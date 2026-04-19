# 后端实现蓝图（FastAPI，当前实现）

## 1. 分层职责
| 层级 | 职责 |
|---|---|
| Router | HTTP 边界、请求校验、SSE 响应输出 |
| Service | owner 鉴权、会话校验、聊天编排、审计调用 |
| Store | 数据读写、会话锁、流序号 |
| OpenHarness Adapter | `mock/library/remote` 三模式流式适配 |
| Core | 认证、错误、配置、限流、SSE 编码 |

## 2. 当前主要模块
- `app/api/v1/routes/cases.py`
- `app/api/v1/routes/sessions.py`
- `app/api/v1/routes/chat.py`
- `app/api/v1/routes/auth.py`
- `app/api/v1/routes/playground.py`
- `app/services/case_service.py`
- `app/services/session_service.py`
- `app/services/chat_service.py`
- `app/services/audit_service.py`
- `app/adapters/openharness_client.py`
- `app/core/store.py`
- `app/core/auth.py`
- `app/core/jwt_utils.py`
- `app/core/rate_limit.py`

## 3. 聊天链路（已实现）
1. 解析 owner（匿名或 JWT）。
2. 校验会话归属与会话状态。
3. 执行限流。
4. 获取会话锁（内存锁或 Redis 锁）。
5. 保存用户消息。
6. 调用 OpenHarness 适配器流式产出。
7. 映射事件并输出 SSE（携带 `trace_id`）。
8. 成功时保存助手消息与审计；失败时输出 `error` + `message_end` 并写失败审计。

## 4. 聊天端点与契约
- `POST /api/v1/sessions/{session_id}/chat`
- `POST /api/v1/sessions/{session_id}/chat/stream`（兼容别名）

两个端点共享同一实现。

## 5. 存储后端策略
| 配置 | 实现 | 适用场景 |
|---|---|---|
| `storage_backend=memory` | `InMemoryStore` | 本地快速联调 |
| `storage_backend=postgres` | `PostgresRedisStore` | 开发/预发环境 |

说明：`postgres` 模式下会话锁与 `seq` 使用 Redis；数据库使用 PostgreSQL。

## 6. 认证策略
| 配置 | 请求要求 |
|---|---|
| `auth_mode=anonymous` | `X-Anonymous-Token` |
| `auth_mode=jwt` | `Authorization: Bearer <access_token>` |

认证相关端点：
- `POST /api/v1/auth/sms/send`
- `POST /api/v1/auth/sms/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`

## 7. OpenHarness 模式
- `oh_use_mock=true`：始终返回内置 mock 流。
- `oh_mode=library`：调用 OpenHarness library runtime。
- `oh_mode=remote`：HTTP 流代理到 `oh_base_url + oh_stream_path`。

## 8. 完成定义（DoD）
- 行为符合 `docs/api/api-contract.md`。
- 错误码符合 `docs/api/error-codes.md`。
- pytest 覆盖主链路、认证、权限、限流、会话生命周期与适配器行为。
