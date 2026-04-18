# 环境与运行手册（开发 + 预发）

## 1. 环境矩阵
| 项目 | 开发环境 | 预发环境 |
|---|---|---|
| PostgreSQL | 本地或 Docker | 托管或共享实例 |
| Redis | 本地或 Docker | 托管或共享实例 |
| OpenHarness | 本地测试地址 | 预发地址 |
| 日志级别 | debug | info |

## 2. 关键环境变量
| 变量 | 必填 | 示例 | 说明 |
|---|---|---|---|
| `storage_backend` | 是 | `memory` / `postgres` | 存储后端切换 |
| `database_url` | `postgres` 模式必填 | `postgresql://...` | PostgreSQL 连接串 |
| `redis_url` | `postgres` 模式必填 | `redis://...` | Redis 连接串 |
| `auth_mode` | 是 | `anonymous` / `jwt` | 认证模式 |
| `jwt_secret_key` | `jwt` 模式必填 | `change-me` | JWT 签名密钥 |
| `oh_base_url` | 是 | `http://localhost:8080` | OpenHarness 地址 |
| `oh_stream_path` | 是 | `/api/v1/stream-run` | OpenHarness 流端点 |
| `oh_api_key` | 是 | `sk-...` | OpenHarness 凭证 |
| `oh_use_mock` | 是 | `true` | 是否启用 mock |
| `app_enable_local_rule_fallback` | 是 | `false` | 本地规则回退开关 |

## 3. 启动检查清单
1. PostgreSQL 与 Redis 连通性正常（仅 `postgres` 模式）。
2. 执行建表脚本：`backend/sql/init_schema.sql`。
3. OpenHarness 连通检查通过（或已启用 `oh_use_mock=true`）。
4. 匿名模式或 JWT 模式鉴权流程可用。
5. `/cases` 与 `/sessions/{id}/chat` smoke 脚本通过。

## 4. 日常巡检清单
- 关注流式错误率与 5xx 比例。
- 关注 `SESSION_LOCKED` 异常趋势。
- 关注 `RATE_LIMITED` 是否异常抬升。
- 关注 `OH_SERVICE_ERROR` 与依赖可用性。

## 5. 故障处理（L1）
1. 收集 `trace_id`、owner、endpoint、时间窗口。
2. 归类故障：认证/限流/锁冲突/依赖异常。
3. 依赖故障时启用降级提示并暂停风险发布。
4. 恢复后执行 smoke 脚本确认主链路可用。
