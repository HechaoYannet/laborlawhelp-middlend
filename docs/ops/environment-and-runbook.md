# Environment and Runbook (Dev + Staging)

## 1. Environment Matrix
| Item | Dev | Staging |
|---|---|---|
| PostgreSQL | local/docker | managed/shared |
| Redis | local/docker | managed/shared |
| OpenHarness | local test endpoint | staging endpoint |
| Log level | debug | info |

## 2. Required Variables
| Env | Required | Example |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql://...` |
| `REDIS_URL` | yes | `redis://...` |
| `JWT_SECRET_KEY` | phase2 | `...` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | phase2 | `15` |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | phase2 | `7` |
| `OH_BASE_URL` | yes | `http://localhost:8080` |
| `OH_API_KEY` | yes | `sk-...` |
| `OH_DEFAULT_WORKFLOW` | yes | `labor_consultation` |
| `APP_ENABLE_LOCAL_RULE_FALLBACK` | yes | `false` |

## 3. Startup Checklist
1. DB and Redis reachable.
2. Migrations applied.
3. OpenHarness endpoint health check passes.
4. Anonymous token flow validates.
5. `/cases` and `/sessions/*/chat` smoke test passes.

## 4. Daily Ops Checklist
- Check stream error ratio.
- Check lock conflicts (`SESSION_LOCKED`) trend.
- Check dependency failures (`OH_SERVICE_ERROR`, `SERVICE_UNAVAILABLE`).
- Check fallback flag count (should remain near zero).

## 5. Incident Handling (L1)
1. Capture `trace_id` and endpoint.
2. Classify as auth/lock/rate/dependency.
3. If dependency outage, switch status page and degrade response message.
4. Confirm recovery with smoke tests.
