# 环境与运行手册（开发 + 预发）

## 1. 环境矩阵
| 项目 | 开发环境 | 预发环境 |
|---|---|---|
| PostgreSQL | 本地或 Docker | 托管或共享实例 |
| Redis | 本地或 Docker | 托管或共享实例 |
| OpenHarness | mock / library / remote | library / remote |
| 日志级别 | debug | info |

## 2. 关键环境变量（`backend/.env`）
| 变量 | 必填 | 示例 | 说明 |
|---|---|---|---|
| `storage_backend` | 是 | `memory` / `postgres` | 存储后端 |
| `database_url` | `postgres` 必填 | `postgresql://...` | PostgreSQL 连接串 |
| `redis_url` | `postgres` 必填 | `redis://...` | Redis 连接串 |
| `auth_mode` | 是 | `anonymous` / `jwt` | 认证模式 |
| `jwt_secret_key` | `jwt` 必填 | `change-me` | JWT 签名密钥 |
| `oh_mode` | 是 | `mock` / `library` / `remote` | OpenHarness 运行模式 |
| `oh_use_mock` | 是 | `true` / `false` | 为 true 时总是 mock |
| `oh_lib_keep_empty_reasoning_content` | 否 | `false` | library 模式下是否保留 assistant tool-call message 的空 `reasoning_content`；默认建议关闭 |
| `oh_base_url` | remote 必填 | `http://localhost:8080` | OpenHarness 地址 |
| `oh_stream_path` | remote 必填 | `/api/v1/stream-run` | OpenHarness 流端点 |
| `oh_api_key` | remote 必填 | `sk-...` | OpenHarness 凭证 |
| `app_enable_local_rule_fallback` | 否 | `false` | 本地规则回退开关 |

配置文件管理：
1. 仓库仅维护 `backend/.env.example` 模板。
2. 本地复制为 `backend/.env` 后填写真实配置。
3. 禁止提交真实密钥、token、私有路径。

## 3. 启动流程
```bash
cd backend
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`postgres` 模式初始化：
```bash
psql -d laborlawhelp -f ./sql/init_schema.sql
psql -d laborlawhelp -f ./sql/migrations/20260419_add_messages_metadata.sql
```

## 4. 测试与巡检
基础测试：
```bash
cd backend
python -m pytest -q
```

Postgres/Redis 集成测试（需 Docker）：
```bash
cd backend
./scripts/run_postgres_integration.sh
```

日常巡检关注：
- 流式错误率、5xx 比例
- `SESSION_LOCKED` 趋势
- `RATE_LIMITED` 趋势
- OpenHarness 上游错误（`OH_*`）
