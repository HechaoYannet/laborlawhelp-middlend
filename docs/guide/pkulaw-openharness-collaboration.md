# PKULaw + OpenHarness 协作文档

## 1. 目标

本文用于说明 `laborlawhelp-middlend` 如何通过 OpenHarness 使用北大法宝 MCP 检索工具，并将检索结果沉淀到中间层 SSE `final` 事件中，支撑以下链路：

```text
前端输入
-> middlend 会话编排
-> OpenHarness library runtime
-> PKULaw MCP 检索
-> references / summary / rule_version
-> 前端展示与后续文书、分流协作
```

适用范围：

- `backend/app/adapters/openharness_client.py`
- `backend/app/services/chat_service.py`
- `backend/tests/test_openharness_client_enrichment.py`

---

## 2. 设计原则

1. `Rule First`
金额、赔偿测算、时效边界优先由规则层或中间层策略控制，不能依赖模型自由推理。

2. `Retrieval As Evidence`
PKULaw 的职责是提供法规、案例、本地化口径与引用校验，不替代规则引擎。

3. `OpenHarness As Orchestrator`
OpenHarness 负责多轮会话、工具调用、MCP 接入和流式事件；midend 负责把工具结果整理为前端可消费的数据结构。

4. `Fail Safe`
PKULaw 不可用时，主链路仍可继续输出分析结果，但必须明确标记“依据待补充校验”。

---

## 3. 当前实现概览

当前已实现能力：

1. OpenHarness library 模式会在每轮提示词中显式要求优先使用 `mcp__pkulaw__*` 工具核查法律依据。
2. library 模式会额外挂载本地 skill `labor_pkulaw_retrieval_flow`，并要求模型先调用 `skill(name="labor_pkulaw_retrieval_flow")` 再走 PKULaw 检索。
3. `oh_lib_tool_policy=legal_minimal` 会把工具面收敛到 `skill`、`mcp__pkulaw__*`、`list_mcp_resources`、`read_mcp_resource`，降低 DeepSeek 在“工具过多”时直接文本回答的概率。
4. `ToolExecutionCompleted.output` 中的 PKULaw 结果会被中间层解析为 `references`。
5. `final` 事件会补全：
   - `summary`
   - `references`
   - `rule_version`
   - `finish_reason`
6. `tool_result` 事件会补充：
   - `result_summary`
   - `references`
7. `oh_use_mock=true` 时，无论 `oh_mode` 是否为 `library`，都会优先走 mock，方便本地联调与测试。

---

## 4. 环境配置

先复制模板文件，再在 `backend/.env` 中启用以下配置：

```bash
cd laborlawhelp-middlend/backend
cp .env.example .env
```

> 请仅在本地 `.env` 填写真实密钥，禁止提交到仓库。

```env
oh_mode=library
oh_use_mock=false

oh_lib_model=deepseek-chat
oh_lib_api_format=openai
oh_lib_base_url=https://api.deepseek.com/v1
oh_lib_api_key=YOUR_MODEL_KEY
oh_lib_tool_policy=legal_minimal

PKULAW_MCP_CONFIG=/home/chen-hao/repositories/pkulaw-mcp-router/pkulaw-mcp-router/config.toml
PKULAW_MCP_TOKEN=YOUR_PKULAW_TOKEN
PKULAW_MCP_ENABLED=true
PKULAW_MCP_SERVER_NAME=pkulaw
```

说明：

1. `PKULAW_MCP_CONFIG` 会被 OpenHarness 的环境覆盖逻辑读取，并自动挂载成 `pkulaw` MCP server。
2. 当前 OpenHarness 代码会通过 `npx -y pkulaw-mcp-router@latest serve --config <config.toml>` 启动本地 stdio MCP。
3. 若 token 不可用，常见现象是：
   - MCP server 连不上
   - 或 server 已连接但返回“没有可用工具”
4. `oh_lib_tool_policy=legal_minimal` 时，middlend 会在 library 模式下把工具面收敛到：
   - `skill`
   - `mcp__pkulaw__*`
   - `list_mcp_resources`
   - `read_mcp_resource`

  这样可以降低 DeepSeek 在“全工具注册”场景下直接文本回答、不触发 function call 的概率。
5. 本地 skill 目录位于：

```text
backend/agent-skills/labor_pkulaw_retrieval_flow/SKILL.md
```

该 skill 的职责不是提供答案，而是把模型拉回一条固定流程：

- 先确认 PKULaw 工具是否可用
- 先检索、后结论
- 没有工具结果时，不得把法条依据表述成“已核验”

---

## 5. 运行时行为

### 5.1 提示词增强

midend 会在发给 OpenHarness 的 prompt 前附加 middleware 指令，核心要求包括：

1. 金额和时效结论不能伪造。
2. 若存在 `skill` 工具，必须先调用 `skill(name="labor_pkulaw_retrieval_flow")`。
3. 若存在 `mcp__pkulaw__*` 工具，必须先用它们核查法律依据。
4. 最终回复应覆盖：
   - 简要结论
   - 事实要点
   - 维权步骤
   - 法律依据
   - 是否建议律师介入

### 5.2 Skill 强制流程

`labor_pkulaw_retrieval_flow` 的核心约束如下：

1. 劳动争议、赔偿、违法解除、本地口径问题优先触发。
2. 在给出法条、本地司法口径、案例支撑前，必须先调用至少一个 `mcp__pkulaw__*` 工具。
3. 若工具不可用或调用失败，必须显式说明“本轮未完成依据核验”。

这意味着我们不是只靠一句“请多用工具”，而是同时使用：

- middleware prompt
- skill 工具
- 最小工具面策略

三层一起把模型推向“先检索、后结论”的路径。

### 5.3 工具结果归一

当 OpenHarness 触发 PKULaw 工具后：

1. `ToolExecutionCompleted.output` 会被尝试按 JSON / Python literal 解析。
2. 中间层会递归提取可能的：
   - `title`
   - `url` / `source_url`
   - `excerpt` / `snippet`
3. 归一为：

```json
{
  "title": "劳动合同法第87条",
  "url": "https://...",
  "snippet": "用人单位违法解除劳动合同的..."
}
```

### 5.4 SSE 出流

`tool_result` 示例：

```json
{
  "tool_name": "mcp__pkulaw__fatiao_keyword",
  "result_summary": "retrieved 1 legal reference(s)",
  "references": [
    {
      "title": "劳动合同法第87条",
      "url": "https://...",
      "snippet": "..."
    }
  ]
}
```

`final` 示例：

```json
{
  "message_id": "msg_xxx",
  "summary": "初步判断：构成违法解除。",
  "references": [
    {
      "title": "劳动合同法第87条",
      "url": "https://...",
      "snippet": "..."
    }
  ],
  "rule_version": "shaanxi.illegal_termination.v1",
  "finish_reason": "stop"
}
```

---

## 6. 推荐的 PKULaw 工具使用策略

结合当前 `pkulaw-mcp-router` 配置，优先建议使用：

1. `mcp__pkulaw__fatiao_keyword`
适合精准查找法条。

2. `mcp__pkulaw__law_search_semantic`
适合法规语义检索。

3. `mcp__pkulaw__case_keyword`
适合案例关键词检索。

4. `mcp__pkulaw__citation_validator`
适合校正模型生成的法条引用。

5. `mcp__pkulaw__doc_link`
适合补充可跳转的法宝链接。

建议按案型固定检索组合，而不是完全依赖模型自由决定。

---

## 7. 联调与验收

### 7.1 本地验证

1. 启动后端：

```bash
cd laborlawhelp-middlend/backend
uv run --with-editable ../../OpenHarness --with-requirements requirements.txt uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

2. 打开联调页：

```text
http://127.0.0.1:8000/playground/
```

3. 发送一个涉及劳动争议依据检索的问题，观察：

   - 是否出现 `tool_call`
   - `tool_name` 是否为 `mcp__pkulaw__...`
   - `tool_result.references` 是否非空
   - `final.references` 是否非空

4. 如需绕过 middlend SSE、直接检查 OpenHarness library 路径，可执行：

```bash
cd laborlawhelp-middlend/backend
PYTHONPATH=.:../../OpenHarness/src uv run --with-editable ../../OpenHarness --with-requirements requirements.txt python scripts/debug_library_tool_path.py
```

重点关注输出：

1. `api_client=OpenAICompatibleClient`
2. `tool_registry_count` 是否只剩下 `skill` 和 PKULaw 检索相关工具
3. 是否出现 `[tool_start] skill`
4. 是否继续出现 `[tool_start] mcp__pkulaw__...`
5. 最终 `[final]` 是否仍然是纯文本无工具调用

### 7.2 自动化测试

推荐执行：

```bash
cd laborlawhelp-middlend/backend
PYTHONPATH=. uv run --with-requirements requirements.txt pytest tests/test_openharness_client_enrichment.py tests/test_playground.py -q
```

关注点：

1. `oh_use_mock=true` 时是否稳定走 mock。
2. library 模式下是否能把 PKULaw 结果沉淀到 `final.references`。

---

## 8. 常见问题

### 8.1 没有触发 PKULaw 工具

优先检查：

1. `PKULAW_MCP_CONFIG` 是否生效。
2. `PKULAW_MCP_TOKEN` 是否有效。
3. OpenHarness runtime 中 `pkulaw` MCP server 是否连接成功。
4. `oh_lib_tool_policy` 是否仍为 `legal_minimal`。
5. 调试日志里是否出现 `skill(name="labor_pkulaw_retrieval_flow")` 的引导和 `openai_stream_once ... request_tools=...`。
6. 模型是否支持工具调用。

### 8.2 触发了工具，但 `references` 为空

可能原因：

1. PKULaw 返回的是纯文本，且没有稳定的结构字段。
2. 返回字段名与当前提取逻辑不匹配。
3. 工具返回的是摘要而不是 citation 对象。

处理建议：

1. 保留原始 tool output 样例。
2. 扩展 `openharness_client.py` 中的引用字段映射。
3. 针对具体服务单独做解析适配。

### 8.3 流式主链路正常，但 `final.rule_version` 不符合预期

当前规则：

1. 优先取请求里的 `policy_version`
2. 否则降级为 `labor_consultation.v1`

如果后续规则服务落地，建议改为由规则工具显式返回。

---

## 9. 后续迭代建议

1. 新增 `calc_compensation_tool`
由规则服务产出结构化金额、口径说明、规则版本。

2. 新增 `mcp_retrieval_tool`
将 PKULaw 的多工具调用封装成一个统一法律依据工具，减少模型自由调用成本。

3. 在消息回读接口中暴露助手 `metadata`
便于后端管理台或前端调试页直接查看 `summary/references/rule_version`。

4. 增加 `pkulaw` 连接状态接口
便于 playground 或运维面板直接显示 MCP 健康状态。
