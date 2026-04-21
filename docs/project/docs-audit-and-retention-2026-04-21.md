# 文档审计与保留清单（2026-04-21）

审计时间：`2026-04-21 20:24 CST`

## 1. 审计方法

本次文档整理遵循 3 条规则：

1. 以当前代码为准。
   重点对照：
   - `backend/app/**`
   - `frontend-sdk/**`
   - 当前 `/api/v1` 实际端点与 SSE 事件契约
2. 时间分组。
   - 已跟踪文档：创建时间取 `git log --diff-filter=A` 的首次提交时间，最近撰写时间取最近一次提交时间。
   - 新增但未提交文档：使用文件系统最近修改时间。
3. 有效性取舍。
   - `保留`：仍能直接指导当前代码开发、联调或运维。
   - `归档`：仍有历史价值，但已被当前文档覆盖、偏计划/迁移/验收、或不再是日常入口。

## 2. 2026-04-19 批次文档

| 原路径 | 创建时间 | 最近撰写时间 | 结论 | 说明 |
|---|---|---|---|---|
| `docs/api/api-contract.md` | `2026-04-19 01:37:32` | `2026-04-21 01:01:27` | 保留 | 当前 `/api/v1` HTTP/SSE 契约事实源。 |
| `docs/api/error-codes.md` | `2026-04-19 01:37:32` | `2026-04-19 11:42:39` | 保留 | 当前错误码、HTTP 映射与流内错误说明仍有效。 |
| `docs/database/schema-and-migration.md` | `2026-04-19 01:37:32` | `2026-04-19 11:42:39` | 保留 | 与 `storage` 模块和 SQL 初始化脚本仍一致。 |
| `docs/database/redis-strategy.md` | `2026-04-19 01:37:32` | `2026-04-19 11:42:39` | 保留 | 与 Redis 锁、seq、限流当前实现仍一致。 |
| `docs/guide/frontend-integration.md` | `2026-04-19 01:37:32` | `2026-04-21 01:01:27` | 保留 | 继续作为中间件对前端的通用接入说明。 |
| `docs/guide/backend-implementation.md` | `2026-04-19 01:37:32` | `2026-04-19 11:42:39` | 归档 | 已被新的当前架构总览覆盖。 |
| `docs/guide/openharness-module-development-and-integration.md` | `2026-04-19 02:36:24` | `2026-04-19 02:36:24` | 保留 | 仍是 OpenHarness 模块对接说明的主文档。 |
| `docs/guide/laborlawhelp-frontend-integration-playbook.md` | `2026-04-19 02:36:24` | `2026-04-21 01:01:27` | 归档 | 更偏向外部前端迁移操作手册，已被当前 SDK/通用接入文档替代。 |
| `docs/guide/pkulaw-openharness-collaboration.md` | `2026-04-19 18:07:52` | `2026-04-20 23:43:32` | 保留 | 当前 PKULaw + OpenHarness 协作策略仍有效。 |
| `docs/middlend-plan.md` | `2026-04-19 01:19:50` | `2026-04-21 01:01:27` | 归档 | 属于阶段性设计基线，已被当前架构总览替代。 |
| `docs/ops/environment-and-runbook.md` | `2026-04-19 01:37:32` | `2026-04-19 11:42:39` | 保留 | 仍是环境变量、启动与巡检的有效入口。 |
| `docs/ops/observability.md` | `2026-04-19 01:37:32` | `2026-04-19 01:37:32` | 保留 | 监控字段与告警建议仍适用。 |
| `docs/ops/deploy-and-rollback.md` | `2026-04-19 01:37:32` | `2026-04-19 11:42:39` | 保留 | 部署与回滚流程仍可沿用。 |
| `docs/project/acceptance-checklist.md` | `2026-04-19 01:37:32` | `2026-04-19 11:42:39` | 归档 | 属于阶段性交付清单，不是当前代码主入口。 |
| `docs/project/anonymous-to-user-migration-template.md` | `2026-04-19 01:37:32` | `2026-04-19 01:37:32` | 归档 | 当前仓库仍保留脚本，但该模板属于专项迁移资料。 |
| `docs/project/document-index.md` | `2026-04-19 01:37:32` | `2026-04-19 11:42:39` | 保留 | 作为精简后现行文档的索引入口继续保留。 |
| `docs/project/glossary.md` | `2026-04-19 01:37:32` | `2026-04-19 01:37:32` | 归档 | 独立价值较低，可转为历史参考。 |
| `docs/project/milestones.md` | `2026-04-19 01:37:32` | `2026-04-19 01:37:32` | 归档 | 纯阶段性计划文档，不再作为当前代码参考。 |
| `docs/project/test-plan.md` | `2026-04-19 01:37:32` | `2026-04-19 18:07:52` | 归档 | 当前测试以实际 `backend/tests/**` 为准，此文档更偏阶段性门禁。 |

## 3. 2026-04-21 批次文档

| 原路径 | 创建时间 | 最近撰写时间 | 结论 | 说明 |
|---|---|---|---|---|
| `docs/project/modularization-update.md` | `2026-04-21 18:43:47` | `2026-04-21 18:43:47` | 归档 | 作为模块化过程记录保留历史价值，但不再作为当前架构主入口。 |
| `docs/ops/openharness-library-debug-2026-04-21.md` | `2026-04-21 20:24:46` | `2026-04-21 20:24:46` | 保留 | 当前 OpenHarness/PKULaw 调试记录仍直接服务运行排障。 |
| `docs/guide/current-architecture.md` | `2026-04-21 20:24:00` | `2026-04-21 20:24:00` | 保留 | 新的当前代码架构总览文档。 |
| `docs/project/docs-audit-and-retention-2026-04-21.md` | `2026-04-21 20:24:00` | `2026-04-21 20:24:00` | 保留 | 本次文档整理与保留策略的事实记录。 |

## 4. 归档目标

本次归档目标统一放入：

`docs/archive/2026-04-21/`

归档后建议保留的历史文件包括：

- `docs/archive/2026-04-21/middlend-plan.md`
- `docs/archive/2026-04-21/guide/backend-implementation.md`
- `docs/archive/2026-04-21/guide/laborlawhelp-frontend-integration-playbook.md`
- `docs/archive/2026-04-21/project/acceptance-checklist.md`
- `docs/archive/2026-04-21/project/anonymous-to-user-migration-template.md`
- `docs/archive/2026-04-21/project/glossary.md`
- `docs/archive/2026-04-21/project/milestones.md`
- `docs/archive/2026-04-21/project/modularization-update.md`
- `docs/archive/2026-04-21/project/test-plan.md`

## 5. 精简后的现行文档清单

精简后建议保留的现行文档为：

### 5.1 架构与接口
- `docs/guide/current-architecture.md`
- `docs/api/api-contract.md`
- `docs/api/error-codes.md`

### 5.2 对接与智能层
- `docs/guide/frontend-integration.md`
- `docs/guide/openharness-module-development-and-integration.md`
- `docs/guide/pkulaw-openharness-collaboration.md`

### 5.3 数据与运维
- `docs/database/schema-and-migration.md`
- `docs/database/redis-strategy.md`
- `docs/ops/environment-and-runbook.md`
- `docs/ops/observability.md`
- `docs/ops/deploy-and-rollback.md`
- `docs/ops/openharness-library-debug-2026-04-21.md`

### 5.4 文档治理
- `docs/project/document-index.md`
- `docs/project/docs-audit-and-retention-2026-04-21.md`

## 6. 本次整理后的原则

1. 日常开发优先看 `current-architecture + api-contract + error-codes`。
2. OpenHarness/PKULaw 相关问题优先看 `openharness-module-development-and-integration.md` 和 `openharness-library-debug-2026-04-21.md`。
3. 历史规划、阶段门禁、迁移模板不删除，但统一下沉到 `docs/archive/2026-04-21/`。
