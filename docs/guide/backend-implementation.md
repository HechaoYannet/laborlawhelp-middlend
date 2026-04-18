# 后端实现蓝图（FastAPI）

## 1. 分层职责
| 层级 | 职责 |
|---|---|
| Router | HTTP 边界、请求校验、SSE 响应组装 |
| Service | owner 鉴权、会话校验、业务编排 |
| Store | 数据读写、分布式锁、流序号 |
| OpenHarness Adapter | LLM 流式代理（mock/real） |
| Core | 认证、错误、限流、配置 |

## 2. 当前实现模块
- `app/api/v1/routes/cases.py`
- `app/api/v1/routes/sessions.py`
- `app/api/v1/routes/chat.py`
- `app/api/v1/routes/auth.py`
- `app/services/case_service.py`
- `app/services/session_service.py`
- `app/services/chat_service.py`
- `app/adapters/openharness_client.py`
- `app/core/store.py`
- `app/core/auth.py`
- `app/core/jwt_utils.py`
- `app/core/rate_limit.py`

## 3. 聊天链路（已实现）
1. 解析 owner（匿名或 JWT 用户）。
2. 校验会话归属与会话状态。
3. 按 owner 限流。
4. 获取会话锁：`session:{session_id}:lock`。
5. 落库用户消息。
6. 调用 OpenHarness 流代理。
7. 按 `seq` 下发 `content_delta`。
8. `final` 时落库助手消息并更新会话统计。

## 4. 存储后端策略
| 配置 | 实现 | 适用场景 |
|---|---|---|
| `storage_backend=memory` | `InMemoryStore` | 本地联调、快速开发 |
| `storage_backend=postgres` | `PostgresRedisStore` | 开发环境/预发环境 |

说明：`postgres` 模式下，聊天锁和流序号由 Redis 提供。

## 5. 认证模式策略
| 配置 | 要求 | 行为 |
|---|---|---|
| `auth_mode=anonymous` | `X-Anonymous-Token` | 绑定匿名 owner |
| `auth_mode=jwt` | `Authorization: Bearer <access_token>` | 强制 JWT 校验 |

认证端点：
- `POST /api/v1/auth/sms/send`
- `POST /api/v1/auth/sms/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`

## 6. OpenHarness 代理策略
- `oh_use_mock=true`：使用内置 mock 响应，保障无依赖联调。
- `oh_use_mock=false`：转发到 `OH_BASE_URL + OH_STREAM_PATH`。
- OpenHarness 异常统一映射为 `OH_SERVICE_ERROR`。

## 7. 并发与幂等
- 会话锁超时默认 30 秒（`session_lock_timeout_seconds`）。
- 并发冲突返回 `409 SESSION_LOCKED`。
- 客户端需保证 `client_seq` 单调递增；服务端按 `seq` 输出流。

## 8. 完成定义（DoD）
- 行为符合 [docs/api/api-contract.md](docs/api/api-contract.md)。
- 错误码符合 [docs/api/error-codes.md](docs/api/error-codes.md)。
- pytest 覆盖主链路、认证、权限、限流与会话生命周期。
