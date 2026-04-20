### 智裁中间件设计文档（当前架构基线）

本文档用于描述 `laborlawhelp-middlend` 在当前代码状态下的稳定架构边界，并避免与历史方案混淆。

---

#### 1. 当前架构与职责

| 层级 | 职责 |
| :--- | :--- |
| 前端 | 输入输出、会话状态管理、SSE 解析与渲染 |
| 中间件（FastAPI） | owner 鉴权、case/session 生命周期、SSE 编排、审计、限流、会话锁 |
| OpenHarness | 智能推理、工具调用、流式事件生产 |

关键原则：
- 前端不承载法律结论主逻辑。
- 中间件负责治理与协议稳定，不直接实现法律规则引擎。
- 智能能力通过 OpenHarness（`mock/library/remote`）接入。
- consultation 正式版以中间件为唯一在线主链路，错误场景返回可重试错误态，不依赖前端本地回退生成结果。

---

#### 2. 核心数据模型（已落地）

- PostgreSQL：`users`、`cases`、`sessions`、`messages`、`audit_logs`
- Redis（`storage_backend=postgres`）：
  - `session:{session_id}:lock`
  - `session:{session_id}:stream:seq`
  - `rate:owner:{owner_id}:{YYYYMMDDHHMM}`

详情以：
- `docs/database/schema-and-migration.md`
- `docs/database/redis-strategy.md`
为准。

---

#### 3. API 边界（已实现）

统一前缀：`/api/v1`

- 案件/会话：`/cases`、`/cases/{case_id}/sessions`、`/sessions/{session_id}/messages`、`/sessions/{session_id}/end`
- 聊天流：`/sessions/{session_id}/chat` 与 `/sessions/{session_id}/chat/stream`（别名）
- 认证：`/auth/sms/send`、`/auth/sms/login`、`/auth/refresh`、`/auth/logout`
- 调试：`/playground/runtime`

> 历史文档中提到的 `/sessions/{session_id}/summary`、`/sessions/{session_id}/document`、`/cases/{case_id}/triage` 当前仓库未实现，不属于现阶段契约。

---

#### 4. 流式事件契约（已实现）

事件类型：
- `message_start`
- `content_delta`
- `tool_call`
- `tool_result`
- `final`
- `error`
- `message_end`

每轮会话会生成 `trace_id` 并写入事件载荷，`final` 事件包含 `finish_reason`。

`tool_result` 在基础字段（`tool_name/result_summary/references/trace_id`）外，已支持可选扩展字段：
- `card_type`
- `card_title`
- `card_payload`
- `card_actions`

用于在前端直接渲染结构化结果卡（要素抽取、赔偿测算、文书生成、律师转介）。

---

#### 5. 认证与运行模式

认证：
- `auth_mode=anonymous`：必须提供 `X-Anonymous-Token`
- `auth_mode=jwt`：必须提供 `Authorization: Bearer <access_token>`

OpenHarness：
- `oh_use_mock=true`：强制 mock
- `oh_mode=library`：OpenHarness library runtime
- `oh_mode=remote`：HTTP 上游流代理

`oh_lib_tool_policy=legal_minimal` 下保留的关键工具面：
- `skill`
- `mcp__pkulaw__*`
- `list_mcp_resources`
- `read_mcp_resource`
- `labor_fact_extract`
- `labor_compensation_calc`
- `labor_document_gen`
- `labor_lawyer_recommend`

---

#### 6. 错误与治理

- 标准错误响应：`code/message/trace_id/retryable/details`
- 聊天失败会返回 SSE `error` 事件并以 `message_end` 收尾
- 审计事件：`turn_completed`、`turn_failed`

---

#### 7. 运行与验证

开发启动、环境变量、测试命令以以下文档为准：
- `docs/ops/environment-and-runbook.md`
- `backend/README.md`
- `docs/project/test-plan.md`

---

#### 8. 文档导航

- API 契约：`docs/api/api-contract.md`
- 错误码：`docs/api/error-codes.md`
- 后端实现：`docs/guide/backend-implementation.md`
- OpenHarness 模块：`docs/guide/openharness-module-development-and-integration.md`
- PKULaw 协作：`docs/guide/pkulaw-openharness-collaboration.md`
- 文档索引：`docs/project/document-index.md`
