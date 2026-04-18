# Acceptance Checklist (Staging)

## 1. Contract Consistency
- [ ] API behavior matches `docs/api/api-contract.md`
- [ ] Error envelope and codes match `docs/api/error-codes.md`
- [ ] SSE event order and schema are consistent across FE/BE docs

## 2. Main Flow
- [ ] can create case and session as anonymous owner
- [ ] chat stream renders token by token with seq ordering
- [ ] summary and references can be queried after stream final

## 3. Stability and Resilience
- [ ] session lock conflict returns `409 SESSION_LOCKED`
- [ ] rate limit returns `429 RATE_LIMITED` and retry policy works
- [ ] dependency errors return mapped code and user-friendly message

## 4. Observability
- [ ] every request has trace_id
- [ ] key metrics visible on dashboard
- [ ] alerts fire and route correctly in staging drill

## 5. Migration Readiness
- [ ] anonymous-to-user migration template reviewed
- [ ] migration rehearsal completed on staging snapshot
- [ ] rollback rehearsal completed

## 6. Performance Gate
- [ ] concurrent sessions >= 200 sustained
- [ ] first token latency p95 <= 2.5s
- [ ] full response latency p95 <= 12s
- [ ] stream error rate <= 1.0%
- [ ] 5xx rate <= 0.5%

## 7. Sign-off
- [ ] FE lead sign-off
- [ ] BE lead sign-off
- [ ] QA sign-off
- [ ] Ops sign-off
