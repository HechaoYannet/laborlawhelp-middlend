# LaborLawHelp Middlend

劳动法律咨询中间层项目，包含后端服务实现、前后端集成文档、运维与测试治理文档，以及联调用脚本。

## 仓库结构

- `backend/`：FastAPI 后端服务、数据库脚本与后端测试
- `docs/`：项目设计、接口协议、开发指南、运维与治理文档
- `frontend-sdk/`：前端流式聊天 SDK 示例
- `scripts/`：仓库级联调脚本（PowerShell）

## 关键文档导航

### 核心设计
- [中间件方案总览](docs/middlend-plan.md)
- [文档索引与角色路径](docs/project/document-index.md)

### API 与协议
- [API Contract](docs/api/api-contract.md)
- [错误码定义](docs/api/error-codes.md)

### 开发集成
- [后端实现指南](docs/guide/backend-implementation.md)
- [前端集成指南](docs/guide/frontend-integration.md)
- [前端集成 Playbook](docs/guide/laborlawhelp-frontend-integration-playbook.md)
- [OpenHarness 模块开发与集成](docs/guide/openharness-module-development-and-integration.md)

### 数据与存储
- [数据库 Schema 与迁移](docs/database/schema-and-migration.md)
- [Redis 策略](docs/database/redis-strategy.md)

### 运维与发布
- [环境与运行手册](docs/ops/environment-and-runbook.md)
- [可观测性](docs/ops/observability.md)
- [部署与回滚](docs/ops/deploy-and-rollback.md)

### 项目治理
- [里程碑](docs/project/milestones.md)
- [测试计划](docs/project/test-plan.md)
- [验收清单](docs/project/acceptance-checklist.md)
- [游客迁移模板](docs/project/anonymous-to-user-migration-template.md)
- [术语表](docs/project/glossary.md)

## 常用入口

- 后端说明与启动：[`backend/README.md`](backend/README.md)
- 后端测试：[`backend/tests/test_smoke.py`](backend/tests/test_smoke.py)
- Postgres/Redis 实链测试脚本：[`backend/scripts/run_postgres_integration.sh`](backend/scripts/run_postgres_integration.sh)
- 前端流式 SDK：[`frontend-sdk/stream-chat.ts`](frontend-sdk/stream-chat.ts)
- 烟雾脚本：[`scripts/smoke-chat.ps1`](scripts/smoke-chat.ps1)

文档源约定：
- OpenHarness 模块开发文档以 `docs/guide/openharness-module-development-and-integration.md` 为单一维护源。
