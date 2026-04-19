# Database Schema and Migration Plan（当前实现）

## 1. 核心表
- `users`
- `cases`
- `sessions`
- `messages`
- `audit_logs`

参考 SQL：`backend/sql/init_schema.sql`

## 2. 关系约束
| From | To | Rule |
|---|---|---|
| `cases.user_id` | `users.id` | 匿名阶段可空 |
| `sessions.case_id` | `cases.id` | 必填 |
| `sessions.user_id` | `users.id` | 匿名阶段可空 |
| `messages.session_id` | `sessions.id` | 必填 |

## 3. 关键索引（已落地）
| 表 | 索引 |
|---|---|
| `cases` | `idx_cases_user_updated`, `idx_cases_anon_updated` |
| `sessions` | `idx_sessions_case_created` |
| `messages` | `idx_messages_session_created` |
| `audit_logs` | `idx_audit_trace` |

## 4. 消息元数据迁移
当前 `messages` 已包含 `metadata JSONB` 字段。

- 基础 schema：`backend/sql/init_schema.sql`
- 增量迁移：`backend/sql/migrations/20260419_add_messages_metadata.sql`

增量迁移可安全重复执行（`ADD COLUMN IF NOT EXISTS`）。

## 5. 迁移执行顺序
1. 执行 `init_schema.sql`（新环境）。
2. 依次执行 `sql/migrations/*.sql`（增量升级）。
3. 运行集成测试验证读写与流式链路。

## 6. 质量门禁
- 在快照库做演练。
- 保证迁移幂等。
- 对 `/cases`、`/sessions`、`/messages` 核心查询做执行计划复核。
