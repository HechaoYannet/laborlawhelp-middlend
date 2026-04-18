# Backend Implementation Blueprint (FastAPI)

## 1. Layering
| Layer | Responsibility |
|---|---|
| Router | HTTP boundary, request validation, response/SSE framing |
| Service | ownership checks, rate limits, lock orchestration |
| OpenHarness Adapter | stream bridge, chunk normalization |
| Repository | DB/Redis read-write |
| Audit | trace logging and compliance records |

## 2. Suggested Module Layout
- `app/api/v1/routes/cases.py`
- `app/api/v1/routes/sessions.py`
- `app/api/v1/routes/chat.py`
- `app/services/chat_service.py`
- `app/services/session_service.py`
- `app/adapters/openharness_client.py`
- `app/repositories/*.py`
- `app/core/auth.py`
- `app/core/rate_limit.py`
- `app/core/sse.py`

## 3. Chat Flow Contract
1. Resolve owner (`anonymous` or `user`).
2. Validate session ownership.
3. Rate limit by owner key.
4. Acquire `session:{session_id}:lock`.
5. Save user message.
6. Proxy OpenHarness stream.
7. Persist assistant message and metadata on `final`.
8. Write audit log.

## 4. Concurrency and Idempotency
- Lock timeout: 30 seconds.
- Duplicate `client_seq` in same session within 5 minutes should be deduped.
- Return `409 SESSION_LOCKED` for parallel submissions.

## 5. Audit Requirements
| Event Type | Required Fields |
|---|---|
| `api_request` | `trace_id`, `owner_type`, `owner_id`, `session_id` |
| `oh_tool_call` | `tool_name`, redacted args summary |
| `oh_final` | response summary, references count, fallback flag |

## 6. Security Requirements
- Mask sensitive identifiers in logs.
- Validate attachment URL scheme as HTTPS.
- Enforce max message length and attachment count.

## 7. Runtime Flags
| Env | Default | Notes |
|---|---|---|
| `APP_ENABLE_LOCAL_RULE_FALLBACK` | `false` | temporary migration flag |
| `OH_DEFAULT_WORKFLOW` | `labor_consultation` | workflow route |

## 8. Definition of Done
- API behavior aligns with `docs/api/api-contract.md`.
- Errors align with `docs/api/error-codes.md`.
- Stream order verified by integration tests.
