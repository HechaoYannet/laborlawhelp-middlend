# 当前中间件架构总览（与当前代码同步）

同步时间：`2026-04-21 20:24 CST`

## 1. 架构主线

当前 `laborlawhelp-middlend` 已经从早期的“按横向层拆分”演进为“按主功能模块拆分”的结构，主线可以归纳为 6 层：

1. 应用装配层：负责 FastAPI 应用创建、中间件、异常处理、根路由、静态资源与生命周期。
2. API 聚合层：负责把 `/api/v1` 下的业务路由按功能模块装配起来。
3. 业务模块层：按认证、案件会话、聊天、存储、调试页拆分，承接真实业务实现。
4. OpenHarness 适配层：负责 `mock / library / remote` 三模式、提示词增强、工具富化、MCP 自愈和流式错误治理。
5. 本地工具层：提供劳动事实提取、赔偿测算、文书生成、律师推荐等结构化工具能力。
6. 前端 SDK 层：把当前中间件的 HTTP/SSE 契约收敛成可复用的前端调用入口。

## 2. 目录结构解释

```text
backend/
  app/
    main.py
    bootstrap.py
    api/v1/router.py
    modules/
      auth/
      case_session/
      chat/
      playground/
      storage/
    adapters/openharness/
    core/
    tools/
    models/schemas.py
    static/playground/
  scripts/
  tests/

frontend-sdk/
  core/
  modules/
  index.ts
  stream-chat.ts
```

## 3. 当前核心链路

### 3.1 启动链路
1. `backend/app/main.py` 只暴露 `app = create_app()`。
2. `backend/app/bootstrap.py` 负责加载 `.env`、注册 CORS、中间件、异常处理、根路由、`/playground` 静态页和 shutdown 钩子。
3. `backend/app/api/v1/router.py` 统一挂载 `auth / case_session / chat / playground` 四组路由。

### 3.2 案件与会话链路
1. 前端通过 `frontend-sdk/modules/case-session.ts` 调 `/api/v1/cases`、`/cases/{case_id}/sessions`。
2. `backend/app/modules/case_session/router.py` 负责 HTTP 参数和响应组装。
3. `backend/app/modules/case_session/service.py` 负责 owner 归属校验、案件/会话查询和消息读取。
4. `backend/app/modules/storage/*` 负责数据落库、会话锁、流序号等基础设施。

### 3.3 聊天流链路
1. 前端通过 `frontend-sdk/modules/chat.ts` 发起 `POST /api/v1/sessions/{session_id}/chat/stream`。
2. `backend/app/modules/chat/router.py` 做会话状态检查和限流检查。
3. `backend/app/modules/chat/service.py` 保存用户消息、消费 OpenHarness chunk、写入助手消息和审计。
4. `backend/app/modules/chat/events.py` 把内部 chunk 转成 SSE 帧。
5. 前端通过 `frontend-sdk/core/sse.ts` 解析 `message_start / content_delta / tool_call / tool_result / final / error / message_end`。

### 3.4 OpenHarness 链路
1. `backend/app/adapters/openharness/client.py` 根据 `oh_use_mock` 与 `oh_mode` 决定走 `mock / library / remote`。
2. `prompting.py` 为劳动争议场景拼接中间件提示词。
3. `local_tools.py` 与 `backend/app/tools/*` 注册本地劳动法工具。
4. `enrichment.py` 从工具输出中提取引用、摘要与卡片数据。
5. `client.py` 负责 MCP 失败后的重连与工具补注册，以及 OpenAI 兼容流式异常的重试与映射。

## 4. 文件职责一句话分析

### 4.1 应用装配层
| 文件 | 一句话职责 |
|---|---|
| `backend/app/main.py` | 保持应用入口极薄，只暴露 `create_app()` 结果。 |
| `backend/app/bootstrap.py` | 统一装配 FastAPI 应用、环境加载、中间件、异常处理、路由与生命周期。 |
| `backend/app/api/v1/router.py` | 聚合 `/api/v1` 下所有业务模块路由。 |

### 4.2 认证模块 `backend/app/modules/auth`
| 文件 | 一句话职责 |
|---|---|
| `__init__.py` | 对外导出认证模块的统一公共接口。 |
| `context.py` | 从匿名 token 或 JWT 中解析当前 owner。 |
| `router.py` | 暴露短信发送、短信登录、刷新 token、登出接口。 |
| `schemas.py` | 定义认证请求体和 token 响应结构。 |
| `service.py` | 承接短信登录与 token 刷新的业务逻辑。 |
| `tokens.py` | 负责 access/refresh token 的生成与解码。 |

### 4.3 案件与会话模块 `backend/app/modules/case_session`
| 文件 | 一句话职责 |
|---|---|
| `__init__.py` | 为案件与会话模块提供统一导出面。 |
| `router.py` | 暴露案件、会话、消息列表、结束会话等 HTTP 接口。 |
| `schemas.py` | 定义案件/会话/消息相关的请求与响应模型。 |
| `service.py` | 封装案件、会话、消息的 owner 校验与存储访问逻辑。 |

### 4.4 聊天模块 `backend/app/modules/chat`
| 文件 | 一句话职责 |
|---|---|
| `__init__.py` | 对外导出聊天模块公共接口。 |
| `router.py` | 暴露聊天 SSE 端点并在进入主链路前做会话状态与限流检查。 |
| `schemas.py` | 定义聊天请求体和附件结构。 |
| `service.py` | 管理一轮聊天的消息落库、OpenHarness 调用、SSE 输出和成功/失败审计。 |
| `events.py` | 把内部 chunk 转换成前端可消费的 SSE 事件。 |
| `audit.py` | 封装聊天成功/失败审计写入逻辑。 |

### 4.5 存储模块 `backend/app/modules/storage`
| 文件 | 一句话职责 |
|---|---|
| `__init__.py` | 暴露存储模块的统一导出接口。 |
| `factory.py` | 根据配置创建并缓存实际使用的 store 实例。 |
| `protocol.py` | 定义存储层抽象协议 `BaseStore`。 |
| `records.py` | 定义案件、会话、消息、审计日志的记录模型。 |
| `memory.py` | 提供本地联调用的内存版存储实现。 |
| `postgres.py` | 提供 PostgreSQL + Redis 的正式存储实现。 |

### 4.6 调试页模块 `backend/app/modules/playground`
| 文件 | 一句话职责 |
|---|---|
| `__init__.py` | 暴露 playground 模块公共接口。 |
| `router.py` | 返回运行时配置摘要，供联调页面读取。 |

### 4.7 OpenHarness 适配层 `backend/app/adapters/openharness`
| 文件 | 一句话职责 |
|---|---|
| `__init__.py` | 暴露 OpenHarness 适配层的公共导出面。 |
| `client.py` | 统一处理 OpenHarness 三模式、流式解析、兼容补丁、MCP 自愈和错误映射。 |
| `prompting.py` | 生成劳动争议场景的增强提示词与规则版本。 |
| `enrichment.py` | 从工具输出中提取引用、摘要、卡片和工具白名单判断。 |
| `local_tools.py` | 组装本地劳动法工具并注册到 OpenHarness runtime。 |
| `types.py` | 定义中间件内部使用的 `OHChunk` 数据结构。 |

### 4.8 横向支撑层 `backend/app/core`
| 文件 | 一句话职责 |
|---|---|
| `config.py` | 管理中间件运行时环境变量与配置校验。 |
| `errors.py` | 定义 `AppError` 与全局异常到标准错误响应的映射。 |
| `rate_limit.py` | 提供内存/Redis 双实现的 owner 限流能力。 |
| `sse.py` | 提供统一的 SSE 帧编码函数。 |

### 4.9 兼容与聚合模型
| 文件 | 一句话职责 |
|---|---|
| `backend/app/models/schemas.py` | 把分模块 schema 聚合成兼容导出入口，减少旧引用迁移成本。 |

### 4.10 本地劳动法工具 `backend/app/tools`
| 文件 | 一句话职责 |
|---|---|
| `__init__.py` | 统一导出本地工具实例。 |
| `labor_fact_extract.py` | 结构化提取劳动争议案情、缺失字段与下一步提问。 |
| `labor_compensation.py` | 按陕西/全国口径计算 N、2N、双倍工资等赔偿项目。 |
| `labor_document.py` | 生成案情摘要、行动清单、仲裁申请书、证据清单等文书。 |
| `labor_lawyer_recommend.py` | 根据案情复杂度输出律师转介与风险标签。 |

### 4.11 前端 SDK `frontend-sdk`
| 文件 | 一句话职责 |
|---|---|
| `index.ts` | 统一导出前端可用的 auth/case-session/chat SDK。 |
| `core/http.ts` | 提供带 owner/JWT 头构造的 JSON 请求封装。 |
| `core/sse.ts` | 提供中间件 SSE 帧解析器。 |
| `modules/auth.ts` | 封装认证相关 HTTP 调用。 |
| `modules/case-session.ts` | 封装案件、会话、消息列表与结束会话调用。 |
| `modules/chat.ts` | 封装聊天 SSE 请求入口。 |
| `stream-chat.ts` | 为匿名 owner 场景保留轻量兼容包装。 |

### 4.12 调试静态页 `backend/app/static/playground`
| 文件 | 一句话职责 |
|---|---|
| `index.html` | 提供联调页骨架。 |
| `app.js` | 实现 playground 的联调脚本逻辑。 |
| `styles.css` | 定义 playground 样式。 |

### 4.13 脚本与测试
| 文件 | 一句话职责 |
|---|---|
| `backend/scripts/debug_library_tool_path.py` | 排查 OpenHarness library 模式下工具注册和调用路径。 |
| `backend/scripts/migrate_anonymous_to_user.py` | 执行匿名 owner 到用户 owner 的迁移脚本。 |
| `backend/scripts/rollback_anonymous_migration.py` | 回滚匿名到用户的迁移。 |
| `backend/scripts/run_postgres_integration.sh` | 启动并执行 Postgres/Redis 集成测试。 |
| `backend/tests/conftest.py` | 为 pytest 注入统一的后端导入路径。 |
| `backend/tests/test_smoke.py` | 覆盖主链路、权限、限流和聊天失败收尾。 |
| `backend/tests/test_playground.py` | 覆盖联调页与运行时摘要接口。 |
| `backend/tests/test_audit_service.py` | 覆盖聊天审计写入逻辑。 |
| `backend/tests/test_openharness_client.py` | 覆盖 remote 模式协议解析与重试行为。 |
| `backend/tests/test_openharness_client_enrichment.py` | 覆盖 library 模式富化、MCP 自愈和兼容补丁。 |
| `backend/tests/integration/test_postgres_streaming.py` | 覆盖 PostgreSQL + Redis 的聊天实链集成。 |

## 5. 当前架构判断

当前代码的主结构已经比较清晰：

- 业务路由基本都收敛到 `backend/app/modules/*`。
- OpenHarness 相关逻辑已经从单文件拆为 `client / prompting / enrichment / local_tools / types`。
- 前端接入层已经形成 `frontend-sdk/core + frontend-sdk/modules` 的独立边界。

当前仍然值得持续关注的热点有两处：

1. `backend/app/adapters/openharness/client.py`
   这是当前最复杂的单点文件，承担了模式切换、兼容补丁、MCP 自愈、错误映射和流式解析。
2. `docs/archive/2026-04-21/project/modularization-update.md`
   它保留了完整的模块化过程记录，适合作为历史资料，但不适合作为当前架构的主入口。

## 6. 推荐阅读顺序

1. `docs/guide/current-architecture.md`
2. `docs/api/api-contract.md`
3. `docs/api/error-codes.md`
4. `docs/guide/frontend-integration.md`
5. `docs/guide/openharness-module-development-and-integration.md`
6. `docs/ops/environment-and-runbook.md`
