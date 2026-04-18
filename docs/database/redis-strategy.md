# Redis Key Strategy and Recovery

## 1. Keyspace
| Key | Type | TTL | Purpose |
|---|---|---|---|
| `owner:{owner_id}:sessions` | Set | no | active sessions |
| `session:{session_id}:lock` | String | 30s | per-session lock |
| `session:{session_id}:stream:seq` | String | session lifecycle | stream sequence |
| `rate:owner:{owner_id}:minute` | String | 60s | per-minute limit |
| `jwt:refresh:{user_id}:{jti}` | String | 7d | refresh deny list |

## 2. Locking Policy
- Acquire lock before chat execution.
- Lock value should include `trace_id` for debugging.
- On stream exit, release lock in `finally` block.

## 3. Rate Limit Policy
- Phase 1 baseline: 20 requests/minute per owner.
- Exceed limit => `429 RATE_LIMITED`.
- Track burst pattern for abuse analysis.

## 4. Stream Seq Policy
- Initialize seq on new session.
- Increment per `content_delta`.
- Include last seq in audit for stream failures.

## 5. Failure Recovery
| Failure | Recovery |
|---|---|
| Redis transient failure | degrade to safe reject (503) |
| Lock key leaked | rely on TTL expiration |
| Seq key missing | reinit and mark recovery in audit |
| Rate key missing | recreate key and continue |

## 6. Ops Notes
- Enable Redis persistence mode according to environment policy.
- Monitor key eviction; lock and seq keys must not be evicted under normal load.
