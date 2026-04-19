# API 契约 v1（与当前代码实现对齐）

## 1. 范围与版本
- 统一前缀：`/api/v1`
- 认证模式：`auth_mode=anonymous` 或 `auth_mode=jwt`
- 本文档是当前后端 HTTP/SSE 行为事实源。

## 2. 通用规则
| 项目 | 规则 |
|---|---|
| 请求体类型 | `application/json` |
| 流式响应类型 | `text/event-stream` |
| 时间格式 | ISO-8601（UTC） |
| 链路追踪 | 服务器为每轮聊天生成 `trace_id`，并写入 SSE 事件 |

## 3. 认证与 owner 归属
| 模式 | 必需请求头 | 行为 |
|---|---|---|
| `anonymous` | `X-Anonymous-Token` | 绑定匿名 owner |
| `jwt` | `Authorization: Bearer <access_token>` | 强制 JWT 校验并绑定用户 owner |

说明：`/cases`、`/sessions`、`/chat` 相关端点均按 owner 做归属校验。

## 4. 已实现端点

### 4.1 案件与会话
| 端点 | 方法 | 说明 |
|---|---|---|
| `/cases` | POST | 创建案件 |
| `/cases` | GET | 查询当前 owner 案件列表 |
| `/cases/{case_id}` | GET | 查询案件详情 |
| `/cases/{case_id}/sessions` | POST | 在案件下创建会话 |
| `/cases/{case_id}/sessions` | GET | 查询案件下会话列表 |
| `/sessions/{session_id}/messages` | GET | 查询会话消息（时间升序，不分页） |
| `/sessions/{session_id}/end` | PATCH | 主动结束会话 |

### 4.2 聊天流
| 端点 | 方法 | 说明 |
|---|---|---|
| `/sessions/{session_id}/chat` | POST | SSE 主端点 |
| `/sessions/{session_id}/chat/stream` | POST | 与 `/chat` 等价的别名端点 |

请求体：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `message` | string | 是 | 1~4000 字 |
| `attachments` | array | 否 | 附件数组 |
| `client_seq` | int | 是 | `>=0` |
| `locale` | string | 否 | 语言偏好 |
| `policy_version` | string | 否 | 规则版本偏好 |
| `client_capabilities` | string[] | 否 | 客户端能力声明 |

附件对象：`id`、`name`、`url`、`mime_type` 均为必填字符串。

### 4.3 认证
| 端点 | 方法 | 说明 |
|---|---|---|
| `/auth/sms/send` | POST | 发送验证码（开发环境模拟） |
| `/auth/sms/login` | POST | 登录并返回 access/refresh token |
| `/auth/refresh` | POST | 刷新 access token |
| `/auth/logout` | POST | 登出（当前为成功占位） |

### 4.4 调试与联调
| 端点 | 方法 | 说明 |
|---|---|---|
| `/playground/runtime` | GET | 返回运行时配置摘要 |
| `/` | GET | 服务健康信息 |
| `/playground/` | GET | 静态联调页面 |

## 5. SSE 事件契约
标准顺序：
1. `message_start`
2. `content_delta`（0..n）
3. `tool_call` / `tool_result`（0..n）
4. `final`（成功路径）
5. `error`（失败路径）
6. `message_end`

事件字段（当前实现）：

- `message_start`: `message_id`, `trace_id`
- `content_delta`: `delta`, `seq`, `trace_id`
- `tool_call`: `tool_name`, `args`, `trace_id`
- `tool_result`: `tool_name`, `result_summary`, `references`, `trace_id`
- `final`: `message_id`, `summary`, `references`, `rule_version`, `finish_reason`, `trace_id`
- `error`: `code`, `message`, `retryable`, `trace_id`
- `message_end`: `message_id`, `trace_id`

## 6. 运行模式约束
| 配置项 | 可选值 | 说明 |
|---|---|---|
| `storage_backend` | `memory` / `postgres` | `postgres` 下会话锁与 seq 使用 Redis |
| `oh_mode` | `mock` / `library` / `remote` | OpenHarness 执行模式 |
| `oh_use_mock` | `true` / `false` | 为 true 时总是走 mock |
| `auth_mode` | `anonymous` / `jwt` | 认证策略 |

## 7. 兼容性规则
- 客户端必须忽略未知字段与未知事件类型。
- 建议优先使用 `/chat/stream` 作为前端流式固定路径；`/chat` 持续兼容。
