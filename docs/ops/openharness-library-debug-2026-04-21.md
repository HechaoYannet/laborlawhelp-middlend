# OpenHarness 库模式排障记录

记录时间：`2026-04-21 20:06:05 CST`

## 1. 背景
- 关联前端仓库：`/home/chen-hao/repositories/laborhelper/laborlawhelp`
- 关联中间层仓库：`/home/chen-hao/repositories/laborhelper/laborlawhelp-middlend`
- 排障场景：前端咨询页通过 middlend 调用 OpenHarness `library` 模式，模型配置为 `deepseek-chat`，同时启用本地劳动法工具和 PKULaw MCP。

## 2. 故障现象
- 前端页面报错位置：`src/app/consultation/page.tsx:750`
- 前端控制台错误：`OpenHarness 服务暂时不可用`
- 后端日志特征：
  - 第一轮 `openai_stream_once` 正常返回 `finish_reason=tool_calls`
  - `labor_fact_extract` 工具执行成功
  - 第二轮 `run_query_turn=2` 发起后，没有产出新的业务 chunk，最终被包装为 `OH_SERVICE_ERROR`

## 3. 排障结论
这次故障不在前端页面本身。`consultation/page.tsx` 只是把 SSE `error` 事件中的 `message` 原样抛出。

真正的问题发生在 middlend 的 OpenHarness library 适配层：工具调用完成后，OpenHarness 会把上一轮 assistant tool-call message 转成 OpenAI 兼容格式，并默认补一个空的 `reasoning_content=""`。对部分“思维模型”这是兼容补丁，但对当前 `deepseek-chat` 组合高概率不兼容，因此在第二轮请求时直接失败，最终在 middlend 中被泛化成 `OpenHarness 服务暂时不可用`。

## 4. 排障过程
1. 检查前端报错链路，确认 `page.tsx` 只是消费后端流式错误，而不是主动生成该错误。
2. 对照 middlend 后端日志，确认第一轮模型调用和 `labor_fact_extract` 工具执行都已成功，失败点在第二轮模型调用。
3. 检查 `backend/app/adapters/openharness/client.py` 与 OpenHarness `openai_client.py` 的消息转换逻辑，定位到 assistant tool-call message 会被补 `reasoning_content=""`。
4. 结合当前服务提供方和模型配置，判断第二轮调用更可能是被这个空字段触发上游拒绝，而不是工具、本地 SSE 或前端 API 契约问题。

## 5. 本次代码变更
### 5.1 变更文件
- `backend/app/adapters/openharness/client.py`
- `backend/app/core/config.py`
- `backend/tests/test_openharness_client_enrichment.py`
- `backend/.env.example`

### 5.2 核心改动
- 在 `backend/app/core/config.py` 新增开关 `oh_lib_keep_empty_reasoning_content`，默认值为 `false`。
- 在 `backend/app/adapters/openharness/client.py` 中新增 assistant message 归一化逻辑：
  - 默认移除空的 `reasoning_content=""`
  - 保留非空 `reasoning_content`
  - 如果未来接入的服务提供方需要旧行为，可通过 `oh_lib_keep_empty_reasoning_content=true` 恢复
- 在 `backend/app/adapters/openharness/client.py` 增加 `oh_library_submit_failed` 异常日志，便于继续定位真实上游错误。
- 在 `backend/tests/test_openharness_client_enrichment.py` 增加两条单测，覆盖“默认移除空 reasoning_content”和“显式开启后保留空 reasoning_content”。
- 在 `backend/.env.example` 补充 `oh_lib_keep_empty_reasoning_content=false` 示例配置。

## 6. 文件职责说明
- `backend/app/adapters/openharness/client.py`
  负责 middlend 与 OpenHarness `library/remote/mock` 三种模式的统一对接；这次新增的是 `library` 模式下 assistant tool-call message 的兼容归一化。
- `backend/app/core/config.py`
  负责后端环境变量配置模型；这次新增的是一个 provider 兼容开关。
- `backend/tests/test_openharness_client_enrichment.py`
  负责验证 OpenHarness library 模式的 enrich 和兼容逻辑；这次新增的是空 `reasoning_content` 的回归测试。
- `backend/.env.example`
  负责给开发环境和排障环境提供配置模板；这次新增的是 `library` 模式兼容开关示例。

## 7. 验证结果
执行命令：

```bash
cd backend
.venv/bin/pytest tests/test_openharness_client_enrichment.py tests/test_openharness_client.py -q
```

结果：

```text
10 passed
```

## 8. 后续建议
- 重启 middlend 后端进程后重新发起一次咨询请求，确认第二轮模型调用是否恢复。
- 如果仍报错，优先查找新增日志：`oh_library_submit_failed`
- 若后续切换到需要保留空 `reasoning_content` 的 provider，再将 `oh_lib_keep_empty_reasoning_content=true` 作为针对性回退开关使用，而不要直接回滚整个适配层改动。

## 9. 补充排查：MCP 首次失败后的会话自愈

补充记录时间：`2026-04-21 20:16:33 CST`

### 9.1 现象
- 运行日志中出现：`mcp=pkulaw:failed`
- 后续工具链只剩：
  - `skill`
  - `list_mcp_resources`
  - `read_mcp_resource`
  - 本地劳动法工具
- 面板结果出现：`list mcp resources` -> `(no MCP resources)`
- 同一会话后续没有自动长出 `mcp__pkulaw__get_article` / `mcp__pkulaw__search_article`

### 9.2 结论
这说明此前的 library bundle 在第一次 `build_runtime()` 时就连接 PKULaw MCP 失败了，而且失败状态被带进了当前会话缓存。

OpenHarness 上游并不是完全“没有重试”：
- 如果某个 `mcp__pkulaw__*` 工具已经注册，并且调用时报连接异常，`McpToolAdapter.execute()` 内部会先 `reconnect_all()` 再重试一次。

但当前场景的问题在于：
- bundle 初次创建时 MCP 连接就失败
- 因此 `tool_registry` 从一开始就没有注册 `mcp__pkulaw__*` 工具
- 模型只能调用 `list_mcp_resources`，而这个工具本身不会触发重连
- 结果就是“一次失败，整会话里都拿不到 PKULaw 工具”

所以，这次用户怀疑“没有重试连接 MCP 服务器，导致连接一次失败就完蛋了”，判断方向是对的，但更准确的说法是：

`已有 MCP 工具调用失败时会重试；首次建 bundle 失败导致 MCP 工具根本没注册时，不会自愈。`

### 9.3 本次补丁
- 在 `backend/app/adapters/openharness/client.py` 的 library 模式提交流程中增加了 MCP 自愈：
  - 如果发现当前 bundle 存在 `failed` 的 MCP 状态，先执行一次 `reconnect_all()`
  - 重连成功后，把新出现的 `mcp__pkulaw__*` 工具同步注册回当前 `tool_registry`
  - 再开始本轮推理
- 新增日志：
  - `oh_library_mcp_reconnect_attempt`
  - `oh_library_mcp_reconnect_complete`
  - `oh_library_mcp_reconnect_failed`

### 9.4 验证
执行命令：

```bash
cd backend
.venv/bin/pytest tests/test_openharness_client_enrichment.py tests/test_openharness_client.py -q
```

结果：

```text
11 passed
```

并补充了回归测试，覆盖“首次 MCP 失败后，在同一会话中重连并补回 `mcp__pkulaw__*` 工具”的场景。

## 10. 补充排查：MCP 已连接但上游模型流式断流

补充记录时间：`2026-04-21 20:24:16 CST`

### 10.1 现象
- 日志已明确显示：
  - `mcp=pkulaw:connected`
  - `tool_names=skill, list_mcp_resources, read_mcp_resource, mcp__pkulaw__get_article, mcp__pkulaw__search_article, ...`
- 说明这时 PKULaw MCP 已经连接成功，且 `mcp__pkulaw__*` 工具已注册进入当前会话。
- 但随后在首轮模型调用阶段出现：

```text
oh_library_error trace_id=... message=Network error: peer closed connection without sending complete message body (incomplete chunked read). Check your internet connection and try again.
```

### 10.2 结论
这次故障已经不再是 MCP 连接问题，而是 OpenAI 兼容流式调用链路被上游中途断流。

更具体地说：
- 出错点发生在 `run_query_turn=1`
- 还没进入工具执行阶段
- 因此不是 PKULaw 工具调用失败
- 是 `deepseek-chat` 的流式响应在首轮请求期间被上游提前关闭

### 10.3 进一步定位
排查 OpenHarness `OpenAICompatibleClient` 后发现，内部 `_is_retryable()` 判定过窄：
- 只认 `ConnectionError` / `TimeoutError` / `OSError`
- 但 OpenAI SDK 常见的 `APIConnectionError` / `APITimeoutError` 并不在原判断里
- 这会导致像 `incomplete chunked read` 这种网络级流中断没有进入内部自动重试

同时，middlend 在收到 OpenHarness `ErrorEvent(recoverable=True)` 时，原先没有立即转成 `AppError` 抛出，而是继续结束循环，最后被 chat 服务兜底成泛化的：

```text
OpenHarness 服务暂时不可用
```

### 10.4 本次补丁
- 在 `backend/app/adapters/openharness/client.py` 中对 OpenHarness 的 `OpenAICompatibleClient._is_retryable()` 进行了本地 monkey patch：
  - 识别 `APIConnectionError`
  - 识别 `APITimeoutError`
  - 识别 `httpx.TransportError`
  - 识别 `incomplete chunked read` / `peer closed connection` / `remote protocol error` 等典型断流特征
- 创建 `OpenAICompatibleClient` 时补充传入 `timeout=settings.oh_read_timeout_sec`
- 在 library 模式收到 `ErrorEvent` 时，立即转换成 `AppError`：
  - `timeout / timed out` 归类为 `OH_UPSTREAM_TIMEOUT`
  - 其他归类为 `OH_SERVICE_ERROR`
  - 原始错误消息保留下来，不再被吞成泛化文案

### 10.5 验证
执行命令：

```bash
cd backend
.venv/bin/pytest tests/test_openharness_client_enrichment.py tests/test_openharness_client.py -q
```

结果：

```text
13 passed
```

新增覆盖包括：
- OpenAI SDK 连接类异常被识别为可重试
- `ErrorEvent` 中的 timeout 文案被正确映射为 `OH_UPSTREAM_TIMEOUT`

### 10.6 当前判断
到这里可以明确区分三类问题：
- `pkulaw:failed`：MCP 初始化失败问题，现已补“同会话重连 + 工具补注册”
- `reasoning_content=""`：DeepSeek tool-call follow-up 兼容问题，现已补兼容归一化
- `incomplete chunked read`：上游模型流式网络中断问题，现已补重试识别和错误透传

如果后续仍失败，优先查看是否出现：
- `OpenAI API request failed (attempt ... retrying ...)`
- `oh_library_error trace_id=... message=...`
- `oh_library_submit_failed ...`

## 11. 补充排查：工作流话术与开场白重复暴露给用户

补充记录时间：`2026-04-21 21:00 CST`

### 11.1 现象
- 在“被口头辞退”等咨询场景中，助手开场会直接输出内部流程描述，例如：
  - `我将按照劳动争议智能分诊工作流为您分析。`
  - `首先，我需要加载工作流技能，然后收集更多信息进行详细分析。`
- 同一轮回复里还可能出现重复自我介绍或重复开场白，导致用户看到类似“先说明流程，再正式回答”的冗余内容。

### 11.2 根因
- middlend 在 `backend/app/adapters/openharness/prompting.py` 中要求模型优先调用 `skill(name="labor-pkulaw-retrieval-flow")`，但此前缺少一条明确约束：
  - 没有禁止把“加载技能 / 按工作流分析 / 先收集信息”这类内部执行过程直接说给用户。
- 结果是模型把系统层内部工作流说明当成了可展示内容。
- 前端流式展示层此前也没有对这类内部流程话术做兜底清洗，因此一旦模型吐出，页面会原样显示。

### 11.3 本次修复
- 在 `backend/app/adapters/openharness/prompting.py` 补充 prompt 约束：
  - 禁止向用户暴露内部执行过程。
  - 禁止输出“我将按照劳动争议智能分诊工作流为您分析”“我需要先加载工作流技能”“我需要先收集更多信息”等流程说明。
  - 要求直接进入案情分析或追问缺失事实。
  - 要求同一轮回答中不要重复自我介绍、开场白或同一句提示语。
- 在 `backend/tests/test_openharness_client_enrichment.py` 增加断言，确保上述 prompt 约束已被注入到增强提示词中。
- 在关联前端仓库 `laborlawhelp/src/app/consultation/page.tsx` 增加展示层兜底：
  - 清洗已知内部流程话术。
  - 对连续重复段落做去重。
  - 这样即使模型偶发吐出相邻重复开场白，也不会直接展示给用户。

### 11.4 影响范围
- 后端主修复点：prompt 策略收紧，防止模型把工作流元信息当作用户可见内容。
- 前端兜底点：流式文本展示与最终 assistant 消息落地前进行轻量清洗。
- 该修复不改变工具调用顺序，也不改变 `skill` 优先执行的总体策略，只改变“哪些内容允许展示给用户”。

### 11.5 验证状态
- 已在后端测试中补充 prompt 注入断言，覆盖“禁止暴露内部执行过程”的约束存在性。
- 前端已补展示层兜底逻辑；建议重新发起一次“口头辞退”咨询，重点确认：
  - 开场不再出现“加载工作流技能”“先收集更多信息”等内部话术。
  - 同一轮回答不再重复自我介绍或重复开场白。
  - 流式输出与最终落库消息保持一致，不再出现前后两段近似重复内容。
