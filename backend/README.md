# 中间件后端说明（第二批实现）

## 1. 环境安装

### 1.1 venv 方式

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env
```

### 1.2 conda 方式（可选）

```powershell
cd backend
conda create -n laborlawhelp-middlend python=3.11 -y
conda activate laborlawhelp-middlend
python -m pip install -r requirements.txt
copy .env.example .env
```

> Linux/macOS 可使用：`cp .env.example .env`。  
> 注意：`.env` 仅用于本地私有配置，不应提交到仓库。

## 2. 启动 API

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 3. 运行模式

- `storage_backend=memory`（默认）：内存模式，适合本地快速联调。
- `storage_backend=postgres`：PostgreSQL + Redis 模式，适合开发/预发。

`postgres` 模式示例（在 `.env` 中覆盖）：

```env
storage_backend=postgres
database_url=postgresql://postgres:postgres@127.0.0.1:5432/laborlawhelp
redis_url=redis://127.0.0.1:6379/0
oh_use_mock=true
oh_connect_timeout_sec=5
oh_read_timeout_sec=60
oh_first_chunk_timeout_sec=15
oh_retry_max_attempts=3
oh_retry_backoff_seconds=1,2,4
auth_mode=anonymous
jwt_secret_key=change-me
```

初始化数据库：

```powershell
psql -d laborlawhelp -f .\sql\init_schema.sql
```

如果是已有库升级到本版本，先执行：

```powershell
psql -d laborlawhelp -f .\sql\migrations\20260419_add_messages_metadata.sql
```

## 4. pytest 测试

```powershell
python -m pytest -q
```

当前测试覆盖：
- 主链路（创建案件 -> 创建会话 -> 流式聊天）
- 权限隔离（跨 owner 访问拒绝）
- 会话结束后聊天
- 消息列表回读
- 限流触发
- JWT 模式登录与刷新

Postgres/Redis 实链集成测试（需本机可用 Docker）：

```bash
cd backend
./scripts/run_postgres_integration.sh
```

可选参数：
- `KEEP_CONTAINERS=1`：测试完成后不自动删除容器，便于手工排障。
- `PG_PORT`、`REDIS_PORT`：自定义本地端口，避免冲突。

## 5. JWT 二期开关

`.env` 设置：

```env
auth_mode=jwt
```

认证接口：
- POST `/api/v1/auth/sms/send`
- POST `/api/v1/auth/sms/login`
- POST `/api/v1/auth/refresh`
- POST `/api/v1/auth/logout`

当 `auth_mode=jwt` 时，业务接口必须携带 `Authorization: Bearer <access_token>`。

## 6. 烟雾测试脚本

```powershell
cd scripts
.\smoke-chat.ps1
```

## 7. 已实现端点
- POST `/api/v1/cases`
- GET `/api/v1/cases`
- GET `/api/v1/cases/{case_id}`
- POST `/api/v1/cases/{case_id}/sessions`
- GET `/api/v1/cases/{case_id}/sessions`
- GET `/api/v1/sessions/{session_id}/messages`
- PATCH `/api/v1/sessions/{session_id}/end`
- POST `/api/v1/sessions/{session_id}/chat`
- POST `/api/v1/sessions/{session_id}/chat/stream`
- POST `/api/v1/auth/sms/send`
- POST `/api/v1/auth/sms/login`
- POST `/api/v1/auth/refresh`
- POST `/api/v1/auth/logout`

## 8. 游客迁移脚本

```powershell
python .\scripts\migrate_anonymous_to_user.py --database-url "postgresql://postgres:postgres@127.0.0.1:5432/laborlawhelp" --anonymous-id "anon-1" --user-id "00000000-0000-0000-0000-000000000001"
python .\scripts\rollback_anonymous_migration.py --database-url "postgresql://postgres:postgres@127.0.0.1:5432/laborlawhelp" --anonymous-id "anon-1" --user-id "00000000-0000-0000-0000-000000000001"
```
