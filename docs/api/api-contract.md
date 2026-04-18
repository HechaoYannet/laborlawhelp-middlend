# API 契约 v1（Markdown 单一事实源）

## 1. 范围与版本
- 统一前缀：`/api/v1`
- 一期认证模式：`auth_mode=anonymous`
- 二期认证模式：`auth_mode=jwt`
- 本文档是 HTTP/SSE 协议唯一事实来源。

## 2. 通用规则
| 项目 | 规则 |
|---|---|
| 请求体类型 | `application/json` |
| 流式响应类型 | `text/event-stream` |
| 时间格式 | ISO-8601（UTC） |
| 主键类型 | 默认 UUID（特殊说明除外） |
| 幂等建议 | `client_seq + session_id` 作为客户端请求序列键 |
| 链路追踪 | 客户端可传 `X-Trace-Id`，服务端缺省自动生成 |

## 3. 认证与归属
| 模式 | 必需请求头 | 服务端行为 |
|---|---|---|
| `anonymous` | `X-Anonymous-Token` | 绑定匿名 owner |
| `jwt` | `Authorization: Bearer <access_token>` | 校验 JWT 并绑定用户 owner |

说明：`/cases`、`/sessions` 全部端点均执行 owner 归属校验。

## 4. 案件与会话接口

### 4.1 `POST /cases`
创建案件。

请求体：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| title | string | 否 | max 200 | 默认 `未命名案件` |
| region_code | string | 否 | max 20 | 默认 `xian` |

响应 `201`：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | case_id |
| owner_type | string | `anonymous` / `user` |
| created_at | string | ISO-8601 |
| title | string | 案件标题 |
| region_code | string | 地域编码 |
| status | string | `active` / `archived` |

### 4.2 `GET /cases`
获取当前 owner 的案件列表。

### 4.3 `GET /cases/{case_id}`
获取案件详情。

### 4.4 `POST /cases/{case_id}/sessions`
在案件下创建会话。

响应 `201`：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | session_id |
| case_id | uuid | 所属案件 |
| status | string | 默认 `active` |
| openharness_session_id | string/null | OpenHarness 会话标识 |

### 4.5 `GET /cases/{case_id}/sessions`
获取案件下会话列表。

### 4.6 `GET /sessions/{session_id}/messages`
获取会话消息列表（按时间升序）。

### 4.7 `PATCH /sessions/{session_id}/end`
主动结束会话。

响应 `200`：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | session id |
| status | string | `ended` |
| ended_at | string | ISO-8601 |

## 5. 聊天流接口

### 5.1 `POST /sessions/{session_id}/chat`
请求体：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| message | string | 是 | 用户输入 |
| attachments | array | 否 | 附件数组 |
| client_seq | int | 是 | 客户端会话内单调递增序号 |

附件对象：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 附件 ID |
| name | string | 是 | 文件名 |
| url | string | 是 | HTTPS 地址 |
| mime_type | string | 是 | 例如 `image/png` |

响应类型：`text/event-stream`

正常事件顺序：
1. `message_start`
2. `content_delta`（0..n）
3. `tool_call` / `tool_result`（0..n）
4. `final`
5. `message_end`

### 5.2 SSE 事件结构

`message_start`

```json
{"message_id":"msg_xxx"}
```

`content_delta`

```json
{"delta":"...","seq":13}
```

`tool_call`

```json
{"tool_name":"intent_router","args":{"topic":"termination"}}
```

`tool_result`

```json
{"tool_name":"intent_router","result_summary":"classified as unlawful termination"}
```

`final`

```json
{"message_id":"msg_xxx","summary":"...","references":[],"rule_version":"v2.2"}
```

`message_end`

```json
{"message_id":"msg_xxx"}
```

`error`

```json
{"code":503,"message":"服务暂时不可用，您可稍后重试。","retryable":true}
```

## 6. 认证接口（二期）
| 端点 | 方法 | 说明 |
|---|---|---|
| `/auth/sms/send` | POST | 发送验证码（当前为开发模拟） |
| `/auth/sms/login` | POST | 验证码登录，返回 access/refresh token |
| `/auth/refresh` | POST | 刷新 access token |
| `/auth/logout` | POST | 登出（当前为接口预留） |

## 7. 运行模式配置约束
| 配置项 | 可选值 | 说明 |
|---|---|---|
| `storage_backend` | `memory` / `postgres` | `postgres` 模式下会话锁与 seq 走 Redis |
| `oh_use_mock` | `true` / `false` | `false` 时走真实 OpenHarness HTTP 流代理 |
| `auth_mode` | `anonymous` / `jwt` | 决定归属解析与认证强制策略 |

## 8. 兼容性规则
- case/session 双层模型在一期到二期保持不变。
- 客户端必须忽略未知响应字段，保证前后兼容。
- SSE 解析器应忽略未知事件类型，避免升级时中断。
