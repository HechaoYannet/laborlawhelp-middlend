# Redis Key Strategy and Recovery（当前实现）

## 1. Keyspace
| Key | Type | TTL | Purpose |
|---|---|---|---|
| `session:{session_id}:lock` | Lock | `session_lock_timeout_seconds`（默认 30s） | 会话级并发锁 |
| `session:{session_id}:stream:seq` | String(counter) | 无显式 TTL | `content_delta` 序号 |
| `rate:owner:{owner_id}:{YYYYMMDDHHMM}` | String(counter) | 60s | 每 owner 每分钟限流 |

## 2. Lock Policy
- 聊天执行前先抢锁。
- 抢锁失败返回 `409 SESSION_LOCKED`。
- 依赖 TTL 自动兜底清理异常锁。

## 3. Rate Limit Policy
- 默认阈值：`rate_limit_per_minute=20`。
- 超限返回 `429 RATE_LIMITED`。
- `storage_backend=postgres` 时优先使用 Redis 计数。

## 4. Redis 异常降级
- 限流：Redis 不可用时回退内存限流（服务级）。
- 会话锁与 seq：在 `postgres` 模式下依赖 Redis，异常会影响该能力可用性。

## 5. Ops Notes
- 为 Redis 设置合理内存与淘汰策略，避免锁与 seq key 被异常淘汰。
- 关注连接错误、超时和 `SESSION_LOCKED` 异常突增。
