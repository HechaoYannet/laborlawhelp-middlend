# Unified Glossary

| Term | Definition |
|---|---|
| owner | Business owner identity of data, either anonymous owner or logged-in user owner |
| owner_type | Owner category, enum: `anonymous` / `user` |
| anonymous_id | Stable identifier for anonymous owner in phase 1 |
| case_id | Top-level case aggregate identifier |
| session_id | Conversation identifier under a case |
| openharness_session_id | Runtime session identifier used by OpenHarness |
| client_seq | Client-side monotonic sequence for request ordering |
| seq | Server stream sequence for `content_delta` ordering |
| trace_id | Request tracing id propagated across services and logs |
| fallback | Flag meaning local rule fallback path is used |
| message_start | SSE event marking assistant message start |
| content_delta | SSE event carrying incremental assistant text |
| final | SSE event carrying structured final payload |
| message_end | SSE event marking stream completion for current assistant message |
