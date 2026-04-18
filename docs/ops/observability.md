# Observability and Alerting

## 1. Structured Log Fields
Required JSON fields:
- `timestamp`
- `trace_id`
- `owner_type`
- `owner_id`
- `session_id`
- `event`
- `duration_ms`
- `fallback`
- `error_code` (if any)

## 2. Metrics
| Metric | Type | Target |
|---|---|---|
| active_sse_connections | gauge | monitor trend |
| chat_first_token_ms | histogram | p95 under threshold |
| chat_full_response_ms | histogram | p95 under threshold |
| oh_success_rate | gauge | >= 99% on staging |
| rate_limited_count | counter | alert on spikes |
| session_locked_count | counter | alert on spikes |
| fallback_triggered_count | counter | should be near zero |

## 3. Alert Suggestions
| Alert | Condition | Severity |
|---|---|---|
| OpenHarness degraded | `oh_success_rate < 95% for 5m` | high |
| Stream latency high | `chat_first_token_ms p95 > 3000ms for 10m` | medium |
| Error burst | `5xx rate > 3% for 5m` | high |
| Lock conflict burst | `session_locked_count > baseline*3` | medium |

## 4. Trace Correlation
- Propagate `X-Trace-Id` through API -> service -> adapter -> audit.
- If absent from client, generate UUID at ingress.

## 5. Dashboard Layout
1. Traffic and connection panel
2. Latency panel (first token / full response)
3. Error and retry panel
4. Dependency health panel
5. Fallback and lock conflict panel
