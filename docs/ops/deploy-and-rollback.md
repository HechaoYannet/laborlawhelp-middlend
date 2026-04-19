# Deployment and Rollback (Dev + Staging)

## 1. Release Strategy
- Environment order: Dev -> Staging.
- Use small-batch canary in staging where possible.
- Keep `app_enable_local_rule_fallback=false` by default.

## 2. Pre-Deploy Checklist
1. Migrations reviewed and approved.
2. API contract change reviewed against frontend compatibility.
3. Smoke test scripts updated.
4. Alert rules enabled.

## 3. Deploy Steps
1. Apply migrations.
2. Deploy API service.
3. Run health check endpoints.
4. Run chat stream smoke case.
5. Confirm log and metrics ingestion.

## 4. Rollback Triggers
| Trigger | Action |
|---|---|
| 5xx > 5% for 10m | rollback service image |
| stream fatal errors spike | rollback service image |
| migration causes data corruption risk | stop write traffic, execute rollback plan |

## 5. Rollback Steps
1. Freeze deploy pipeline.
2. Roll back service version.
3. Validate endpoints and stream flow.
4. If schema rollback needed, execute prepared rollback script.
5. Publish incident timeline with trace samples.

## 6. Post-Rollback Validation
- `/cases` and `/sessions/{id}/chat` pass smoke tests.
- Error ratio returns to baseline.
- No active lock leak in Redis.
