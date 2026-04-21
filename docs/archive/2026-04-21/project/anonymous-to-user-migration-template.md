# Anonymous to User Migration Template

## 1. Purpose
Migrate anonymous owner data to authenticated user owner without changing case/session model.

## 2. Preconditions
1. User authentication is enabled (phase 2).
2. Migration window and rollback owner are assigned.
3. Backup snapshot is available.

## 3. Mapping Rules
| Source | Target | Rule |
|---|---|---|
| `cases.owner_type='anonymous'` | `cases.owner_type='user'` | switch only after user binding |
| `cases.anonymous_id` | `cases.user_id` | map by verified login event |
| `sessions.anonymous_id` | `sessions.user_id` | same mapping as case owner |

## 4. Idempotent SQL Template

```sql
-- Step 1: bind user_id while keeping anonymous fields
UPDATE cases c
SET user_id = :user_id,
    updated_at = NOW()
WHERE c.anonymous_id = :anonymous_id
  AND c.user_id IS NULL;

UPDATE sessions s
SET user_id = :user_id,
    last_active_at = NOW()
WHERE s.anonymous_id = :anonymous_id
  AND s.user_id IS NULL;

-- Step 2: switch owner_type after binding confirmation
UPDATE cases c
SET owner_type = 'user',
    updated_at = NOW()
WHERE c.anonymous_id = :anonymous_id
  AND c.user_id = :user_id
  AND c.owner_type = 'anonymous';
```

## 5. Audit Record Requirements
- `trace_id`
- migration batch id
- row counts (cases/sessions)
- operator id
- rollback pointer id

## 6. Rollback Template

```sql
UPDATE cases
SET owner_type = 'anonymous',
    user_id = NULL,
    updated_at = NOW()
WHERE anonymous_id = :anonymous_id
  AND user_id = :user_id;

UPDATE sessions
SET user_id = NULL,
    last_active_at = NOW()
WHERE anonymous_id = :anonymous_id
  AND user_id = :user_id;
```

## 7. Validation Checklist
1. Case count before/after matches.
2. Session count before/after matches.
3. Anonymous owner cannot access migrated user-owned session.
4. Audit logs present and queryable by batch id.
