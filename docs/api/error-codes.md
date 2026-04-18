# Error Codes and Handling

## 1. HTTP Mapping
| HTTP | Code | Meaning | Retry | Frontend Action |
|---|---|---|---|---|
| 400 | `BAD_REQUEST` | Invalid parameters | no | Show validation hint |
| 401 | `UNAUTHORIZED` | Invalid/expired auth | no | Trigger login (phase 2) |
| 403 | `FORBIDDEN` | Session/case not owned by caller | no | Navigate back to case list |
| 409 | `SESSION_LOCKED` | Concurrent message conflict | yes | Retry with backoff |
| 410 | `ANONYMOUS_SESSION_EXPIRED` | Anonymous session expired | no | Create new session |
| 429 | `RATE_LIMITED` | Rate limit exceeded | yes | Exponential backoff |
| 500 | `OH_SERVICE_ERROR` | OpenHarness error | yes | Friendly retry prompt |
| 503 | `SERVICE_UNAVAILABLE` | Dependency unavailable | yes | Degrade and retry |

## 2. Error Envelope

```json
{
  "code": "RATE_LIMITED",
  "message": "请求过于频繁，请稍后再试",
  "trace_id": "7ec43fd8-4fa4-4ae0-8f69-0c44f2b726d5",
  "retryable": true,
  "details": {}
}
```

## 3. SSE Error Event

Server must emit this frame before closing stream:

```text
event: error
data: {"code":503,"message":"服务暂时不可用，您可稍后重试。","retryable":true}
```

## 4. Client Retry Policy
| Case | Strategy |
|---|---|
| `SESSION_LOCKED` | Retry in 1s, max 3 attempts |
| `RATE_LIMITED` | Backoff: 1s, 2s, 4s, then fail |
| `OH_SERVICE_ERROR` | Retry once, then show fallback suggestion |
| `SERVICE_UNAVAILABLE` | Retry once after 2s, then stop |

## 5. Logging Requirement
- All error responses include `trace_id`.
- `audit_logs` must record error code and abbreviated message.
- Stream errors must include last delivered `seq` for debugging.
