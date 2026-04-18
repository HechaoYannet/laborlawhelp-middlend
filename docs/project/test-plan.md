# Test Plan (M3 Gate)

## 1. Test Scope
- API contract correctness
- SSE stream ordering and stability
- Ownership and auth checks
- Concurrency lock behavior
- Rate limit behavior
- Dependency failure behavior
- Migration safety checks

## 2. Functional Cases
| ID | Case | Expected |
|---|---|---|
| F-01 | create case -> create session -> chat | full success flow |
| F-02 | access foreign session | `403 FORBIDDEN` |
| F-03 | invalid payload | `400 BAD_REQUEST` |
| F-04 | end session then chat | proper session status handling |

## 3. SSE Cases
| ID | Case | Expected |
|---|---|---|
| S-01 | normal stream | ordered events end with `message_end` |
| S-02 | chunk split | parser still reconstructs frames |
| S-03 | reconnect with seq | no duplicate rendering |
| S-04 | stream error | emits `error` frame with retryable flag |

## 4. Concurrency and Rate
| ID | Case | Expected |
|---|---|---|
| C-01 | parallel chat same session | one request gets `409 SESSION_LOCKED` |
| C-02 | high-frequency requests | `429 RATE_LIMITED` with retry hint |

## 5. Failure Injection
| ID | Case | Expected |
|---|---|---|
| X-01 | OpenHarness timeout | `500/503` mapped and audited |
| X-02 | Redis unavailable | safe fail path, no partial stream corruption |

## 6. Performance Baseline (Staging Gate)
| Metric | Threshold |
|---|---|
| Concurrent sessions | >= 200 sustained |
| First token latency p95 | <= 2.5s |
| Full response latency p95 | <= 12s |
| Stream error rate | <= 1.0% |
| 5xx rate | <= 0.5% |

## 7. Entry and Exit Criteria
- Entry: APIs deployed to staging and observability enabled.
- Exit: all P0/P1 tests pass and performance thresholds met.
