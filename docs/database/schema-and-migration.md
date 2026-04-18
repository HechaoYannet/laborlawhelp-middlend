# Database Schema and Migration Plan

## 1. Core Tables
- `users`
- `cases`
- `sessions`
- `audit_logs`

## 2. Relational Constraints
| From | To | Rule |
|---|---|---|
| `cases.user_id` | `users.id` | nullable in phase 1 |
| `sessions.case_id` | `cases.id` | required |
| `sessions.user_id` | `users.id` | nullable in phase 1 |

## 3. Index Recommendations
| Table | Index | Purpose |
|---|---|---|
| `cases` | `(owner_type, anonymous_id, updated_at desc)` | owner case listing |
| `cases` | `(user_id, updated_at desc)` | logged-in listing |
| `sessions` | `(case_id, created_at desc)` | session history |
| `sessions` | `(anonymous_id, last_active_at desc)` | anonymous recovery |
| `audit_logs` | `(trace_id)` | trace lookup |
| `audit_logs` | `(session_id, created_at desc)` | compliance review |

## 4. Data Retention
- `sessions`: active data retained permanently unless deleted by policy.
- `audit_logs`: retain >= 3 years (configurable by compliance policy).
- Soft-delete is preferred over hard-delete for legal auditability.

## 5. Migration Rules
1. Migration scripts must be forward-only.
2. Each migration includes rollback note even if irreversible.
3. Apply in order: schema -> index -> backfill -> constraints.
4. Zero-downtime rule: add nullable fields first, then backfill, then enforce constraints.

## 6. Example Migration Sequence
1. Add `owner_type` and `anonymous_id` to `cases`.
2. Backfill existing rows to `owner_type='anonymous'` if no `user_id`.
3. Add index for owner listing.
4. Add check constraint for owner consistency.

## 7. Quality Gates
- Migration tested on snapshot copy.
- Backfill script idempotent.
- Runtime query plan reviewed for top 3 endpoints.
