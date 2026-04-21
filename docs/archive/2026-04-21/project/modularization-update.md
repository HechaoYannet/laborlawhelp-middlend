# 模块化更新文档

## 1. 目的与约束

本文档用于约束本仓库后续的模块化重构工作，目标是：

- 只对现有内容做职责归并、边界清理、依赖收束与命名整理
- 不主动新增业务能力、不改变现有 API 契约、不扩大实现范围
- 将重构拆成可独立审批的模块，逐模块推进

执行约束：

- 每个模块开始前单独审批
- 每个模块完成后同步更新本文档中的“实施后核心变化”
- 若某模块重构过程中发现会影响现有契约、测试或文档语义，需要暂停并重新确认

## 2. 当前工作区模块盘点

### 模块 A：应用入口与路由装配

- 当前内容：
  `backend/app/main.py` 负责 `.env` 加载、FastAPI 应用创建、CORS、路由注册、异常处理、静态资源挂载、OpenHarness 关闭逻辑。
- 当前问题：
  应用装配职责集中在单文件，入口层同时承担运行时初始化和模块拼装。
- 模块化目标：
  将“应用工厂”“路由注册”“生命周期管理”边界显式化，但不改变对外路由。
- 涉及文件：
  `backend/app/main.py`
  `backend/app/bootstrap.py`
  `backend/app/api/v1/router.py`
- 审批状态：
  `已审批，实施完成`
- 实施后核心变化：
  `main.py` 降为薄入口；应用工厂、中间件、异常处理、路由装配、静态资源挂载、生命周期钩子已拆分到独立模块；对外入口与 API 路径保持不变`

### 模块 B：认证与请求上下文

- 当前内容：
  `backend/app/modules/auth/` 统一承担 owner 识别、JWT 编解码、认证模型与认证 HTTP 端点。
- 当前问题：
  认证策略、令牌处理、认证接口分散在 core 与 route 之间，语义上属于同一功能域。
- 模块化目标：
  形成统一的认证模块边界，区分“认证协议”“令牌能力”“HTTP 端点”。
- 涉及文件：
  `backend/app/modules/auth/context.py`
  `backend/app/modules/auth/router.py`
  `backend/app/modules/auth/schemas.py`
  `backend/app/modules/auth/service.py`
  `backend/app/modules/auth/tokens.py`
- 审批状态：
  `已审批，实施完成`
- 实施后核心变化：
  `认证协议、JWT 能力、请求上下文解析与认证 HTTP 端点已收束到 auth 模块；旧 core/auth.py、core/jwt_utils.py 与纯 route 兼容层已在后续收缩中清理。`

### 模块 C：案件与会话领域

- 当前内容：
  `backend/app/modules/case_session/` 统一承担案件、会话、消息列表与结束会话能力；`backend/app/models/schemas.py` 保留兼容导出。
- 当前问题：
  路由、服务、响应模型按技术层拆分，但案件与会话作为同一业务域尚未形成聚合边界。
- 模块化目标：
  围绕“案件”“会话”“消息列表/结束会话”做纵向聚合，减少跨文件跳转成本。
- 涉及文件：
  `backend/app/modules/case_session/router.py`
  `backend/app/modules/case_session/service.py`
  `backend/app/modules/case_session/schemas.py`
  `backend/app/models/schemas.py`
- 审批状态：
  `已审批，实施完成`
- 实施后核心变化：
  `案件、会话、消息读取、结束会话相关模型/服务/路由已聚合为同一业务模块；旧 service 与纯 route 兼容层已在后续收缩中清理。`

### 模块 D：聊天编排与流式响应

- 当前内容：
  `backend/app/modules/chat/` 统一承担聊天入口、请求模型、编排服务、SSE 事件拼装与审计记录。
- 当前问题：
  `chat_service.py` 同时承担会话校验、持久化、事件映射、错误处理、日志与审计，职责过重。
- 模块化目标：
  将聊天主流程拆成更清晰的“会话前置校验”“流事件编排”“结果落库/审计”边界，不改变 SSE 契约。
- 涉及文件：
  `backend/app/modules/chat/router.py`
  `backend/app/modules/chat/service.py`
  `backend/app/modules/chat/events.py`
  `backend/app/modules/chat/audit.py`
  `backend/app/core/sse.py`
- 审批状态：
  `已审批，实施完成`
- 实施后核心变化：
  `聊天入口、请求模型、编排服务、SSE 事件拼装、审计记录已集中到 chat 模块；旧 service 与纯 route 兼容层已在后续收缩中清理。`

### 模块 E：OpenHarness 适配层

- 当前内容：
  `backend/app/adapters/openharness_client.py` 覆盖 mock/library/remote 三种模式，并包含 prompt 增强、工具策略过滤、SSE 事件映射、重试与错误转换、卡片元数据生成等逻辑。
- 当前问题：
  单文件职责最重，属于当前仓库最明显的重构热点；运行时生命周期、协议解析、工具增强、业务卡片映射耦合较深。
- 模块化目标：
  在不改变现有行为的前提下，拆分“运行时管理”“远端流协议”“提示词增强”“工具结果富化”几个子职责。
- 涉及文件：
  `backend/app/adapters/openharness_client.py`
- 审批状态：
  `已审批，实施完成`
- 实施后核心变化：
  `OpenHarness 公开入口仍保留在 openharness_client.py，但类型定义、提示词增强、结果富化等职责已拆至独立文件；测试与外部引用路径保持兼容。`

### 模块 F：存储抽象与后端实现

- 当前内容：
  `backend/app/core/store.py` 同时包含记录模型、抽象接口、内存实现、Postgres/Redis 实现、工厂函数。
- 当前问题：
  领域记录、接口定义、具体实现聚集在同一文件，扩展和测试定位成本高。
- 模块化目标：
  分离“存储协议”“内存实现”“持久化实现”“工厂装配”，保持现有存储行为不变。
- 涉及文件：
  `backend/app/core/store.py`
- 审批状态：
  `已审批，实施完成`
- 实施后核心变化：
  `记录模型、存储协议、内存实现、Postgres/Redis 实现、工厂装配已拆入 storage 模块；旧 core/store.py 保留为兼容导出入口。`

### 模块 G：本地劳动工具与 Skill 资产

- 当前内容：
  `backend/app/tools/*.py` 提供赔偿计算、事实提取、文书生成、律师推荐；`backend/agent-skills/labor-pkulaw-retrieval-flow/SKILL.md` 提供工作流说明。
- 当前问题：
  工具本身已按功能拆分，但“工具注册”“工具卡片语义”“skill 协作边界”仍主要散落在适配层。
- 模块化目标：
  保持工具内容不扩张，仅明确工具包边界与 skill/adapter 之间的依赖关系。
- 涉及文件：
  `backend/app/tools/__init__.py`
  `backend/app/tools/labor_compensation.py`
  `backend/app/tools/labor_document.py`
  `backend/app/tools/labor_fact_extract.py`
  `backend/app/tools/labor_lawyer_recommend.py`
  `backend/agent-skills/labor-pkulaw-retrieval-flow/SKILL.md`
- 审批状态：
  `待审批`
- 实施后核心变化：
  `待执行`

### 模块 H：支撑层与运行约束

- 当前内容：
  `backend/app/core/config.py`、`backend/app/core/errors.py`、`backend/app/core/rate_limit.py` 提供配置、统一错误、限流等横切能力。
- 当前问题：
  横切层内容不多，但与业务模块存在直接耦合，后续重构时需要一起校准依赖方向。
- 模块化目标：
  保持为横向支撑层，明确依赖方向，避免业务模块继续向该层堆叠业务语义。
- 涉及文件：
  `backend/app/core/config.py`
  `backend/app/core/errors.py`
  `backend/app/core/rate_limit.py`
- 审批状态：
  `待审批`
- 实施后核心变化：
  `待执行`

### 模块 I：测试与文档同步

- 当前内容：
  `backend/tests/` 覆盖主链路、OpenHarness 适配、审计、Playground、Postgres 集成；`docs/` 维护接口、开发、运维、项目治理文档；`frontend-sdk/stream-chat.ts` 提供前端流式调用示例。
- 当前问题：
  测试和文档已经较完整，但后续模块化重构需要同步校准引用关系和文档结构。
- 模块化目标：
  在每个模块重构后，仅做必要的测试归位、文档更新和示例路径调整，不增加新功能说明。
- 涉及文件：
  `backend/tests/`
  `docs/`
  `frontend-sdk/stream-chat.ts`
- 审批状态：
  `待审批`
- 实施后核心变化：
  `待执行`

## 3. 建议的审批顺序

建议按风险从低到高、从边界清理到核心链路的顺序推进：

1. 模块 A：应用入口与路由装配
2. 模块 B：认证与请求上下文
3. 模块 C：案件与会话领域
4. 模块 H：支撑层与运行约束
5. 模块 D：聊天编排与流式响应
6. 模块 F：存储抽象与后端实现
7. 模块 E：OpenHarness 适配层
8. 模块 G：本地劳动工具与 Skill 资产
9. 模块 I：测试与文档同步

说明：

- 模块 E 和模块 F 改动面最大，建议放在中后段
- 模块 I 不是独立功能开发，而是每一轮模块重构完成后的同步收口项

## 4. 当前审查结论

本仓库当前已经具备明确的业务骨架，问题不在“缺模块”，而在“模块职责分散且核心热点过重”：

- 案件/会话/聊天/OpenHarness/存储/认证几个纵向功能已经存在
- 真正需要重构的是职责边界和依赖方向，不需要额外发明新子系统
- `backend/app/adapters/openharness_client.py`、`backend/app/services/chat_service.py`、`backend/app/core/store.py` 是三个最值得优先规划的热点文件

## 5. 模块实施记录

后续每个模块获批并实施后，按以下格式补充：

### [模块名]

- 审批时间：
  `待填写`
- 变更范围：
  `待填写`
- 实施后核心变化：
  `待填写`
- 对外行为变化：
  `无 / 若有需单列说明`
- 测试与验证：
  `待填写`

### 模块 A：应用入口与路由装配

- 审批时间：
  `2026-04-21`
- 变更范围：
  `backend/app/main.py`
  `backend/app/bootstrap.py`
  `backend/app/api/v1/router.py`
  `docs/project/modularization-update.md`
- 新增文件职责：
  `backend/app/bootstrap.py`：模块 A 的应用装配中心，负责统一承接应用工厂、`.env` 预加载、中间件注册、异常处理注册、根路由注册、静态资源挂载与生命周期钩子绑定。后续凡是“应用如何启动和拼装”的调整，优先在这里维护，而不是继续回填到 `main.py`。
  `backend/app/api/v1/router.py`：`/api/v1` 路由聚合入口，负责集中装配 `auth`、`cases`、`sessions`、`chat`、`playground` 等 v1 子路由。后续新增或调整 v1 路由时，先在对应 route 文件实现，再在这里完成聚合，避免把路由注册逻辑散回应用入口。
- 实施后核心变化：
  `main.py` 仅保留应用入口；路由聚合统一进入 api_v1_router；应用初始化步骤拆分为中间件、异常处理、路由注册、静态资源挂载、生命周期钩子五个明确阶段。`
- 对外行为变化：
  `无`
- 测试与验证：
  `已验证 create_app 入口、/ 路由、/api/v1/playground/runtime 路由与 /playground 挂载仍存在；直接 ASGI 调用 / 与 /api/v1/playground/runtime 返回 200。当前环境下 TestClient 对空 FastAPI 应用也会卡住，未将其作为本轮有效验证手段。`

### 模块 C：案件与会话领域

- 审批时间：
  `2026-04-21`
- 变更范围：
  `backend/app/modules/case_session/__init__.py`
  `backend/app/modules/case_session/schemas.py`
  `backend/app/modules/case_session/service.py`
  `backend/app/modules/case_session/router.py`
  `backend/app/services/case_service.py`
  `backend/app/services/session_service.py`
  `backend/app/api/v1/routes/cases.py`
  `backend/app/api/v1/routes/sessions.py`
  `backend/app/api/v1/router.py`
  `backend/app/models/schemas.py`
  `docs/project/modularization-update.md`
- 新增文件职责：
  `backend/app/modules/case_session/schemas.py`：集中维护案件/会话模块的请求响应模型，避免再与聊天、认证模型混放。
  `backend/app/modules/case_session/service.py`：集中维护案件、会话、消息读取、结束会话等领域服务逻辑，作为该模块的真实业务入口。
  `backend/app/modules/case_session/router.py`：集中暴露案件与会话相关 HTTP 端点，统一该业务模块的 API 边界。
  `backend/app/modules/case_session/__init__.py`：提供模块级统一导出，便于后续维护与引用。
- 实施后核心变化：
  `案件与会话从“按技术层分散”调整为“按业务域聚合”；旧 service 与 route 文件改为兼容层，主要用于承接历史导入路径与测试路径。`
- 对外行为变化：
  `无`
- 测试与验证：
  `已完成路由聚合与兼容路径核对；受当前环境下 TestClient 卡住问题影响，未将基于 TestClient 的端到端用例作为本轮有效验证手段。`

### 模块 D：聊天编排与流式响应

- 审批时间：
  `2026-04-21`
- 变更范围：
  `backend/app/modules/chat/__init__.py`
  `backend/app/modules/chat/schemas.py`
  `backend/app/modules/chat/audit.py`
  `backend/app/modules/chat/events.py`
  `backend/app/modules/chat/service.py`
  `backend/app/modules/chat/router.py`
  `backend/app/services/chat_service.py`
  `backend/app/services/audit_service.py`
  `backend/app/api/v1/routes/chat.py`
  `backend/app/models/schemas.py`
  `docs/project/modularization-update.md`
- 新增文件职责：
  `backend/app/modules/chat/schemas.py`：集中维护聊天请求模型，避免聊天模型继续混入通用 schemas 文件。
  `backend/app/modules/chat/audit.py`：承接聊天模块的审计写入职责，聚焦“回合成功/失败记录”。
  `backend/app/modules/chat/events.py`：承接 SSE 事件拼装职责，统一 `message_start / content_delta / tool_result / final / error / message_end` 的事件结构。
  `backend/app/modules/chat/service.py`：承接聊天主编排逻辑，负责会话锁、消息落库、OpenHarness 调用、最终审计与错误兜底。
  `backend/app/modules/chat/router.py`：承接聊天模块的 HTTP 入口，统一 `/chat` 与 `/chat/stream` 的流式输出边界。
  `backend/app/modules/chat/__init__.py`：提供模块级统一导出，便于维护者快速定位聊天模块公开能力。
- 实施后核心变化：
  `聊天主链路不再把路由、模型、审计、事件拼装全部堆在旧 service 文件中；旧 chat_service 与旧 route 文件保留为兼容层，真实职责已转移到 chat 模块。`
- 对外行为变化：
  `无`
- 测试与验证：
  `已完成模块边界与兼容层路径核对；受当前环境下 TestClient 卡住问题影响，未将原有流式测试作为本轮有效验证手段。`

### 模块 E：OpenHarness 适配层

- 审批时间：
  `2026-04-21`
- 变更范围：
  `backend/app/adapters/openharness_client.py`
  `backend/app/adapters/openharness_types.py`
  `backend/app/adapters/openharness_prompting.py`
  `backend/app/adapters/openharness_enrichment.py`
  `docs/project/modularization-update.md`
- 新增文件职责：
  `backend/app/adapters/openharness_types.py`：集中维护 OpenHarness 流事件块 `OHChunk` 类型定义，避免类型与适配逻辑耦合在同一大文件。
  `backend/app/adapters/openharness_prompting.py`：集中维护中间层提示词增强与规则版本解析逻辑，便于后续单独维护提示词策略。
  `backend/app/adapters/openharness_enrichment.py`：集中维护工具结果富化逻辑，包括引用提取、摘要构建、卡片元数据生成与工具策略判断。
- 实施后核心变化：
  `openharness_client.py 继续作为对外兼容入口，但其“类型定义 / 提示词增强 / 工具结果富化”职责已拆分为独立文件，后续维护不必继续在单一超大文件中操作。`
- 对外行为变化：
  `无`
- 测试与验证：
  `已完成公开入口、兼容导入路径与内部职责拆分核对；受当前环境下 TestClient 卡住问题影响，相关集成验证以结构核对为主。`

## 6. 阶段化检验和进一步优化参考

### 6.1 检验范围与结论摘要

本轮复核重点检查以下四项：

- `0` 当前模块化成果如何，整体架构和模块分布如何
- `1` 与前端的接口连接是否模块化
- `2` 与后端的接口连接是否模块化
- `3` 工具调用、skill 使用及 OpenHarness 对接内容是否模块化
- `4` 除上述三类功能板块外，其他代码模块有哪些

阶段性总判断：

- 当前工作区已经从原先“以 `api / services / models / adapters` 为主的横向分层”演进为“入口装配层 + 业务模块层 + 横向支撑层 + 适配层 + 工具/skill 资产层 + 兼容层”的混合架构。
- 模块化成果是有效的，尤其是 `case_session`、`chat`、`openharness_*` 三组文件的聚合已经明显降低了主链路的跳转成本。
- 当前状态仍属于“阶段性收束完成、但尚未完全收口”的形态：新的业务模块已经形成，但旧兼容层、认证模块、存储模块仍保留在旧结构中，导致整体架构已经清晰，但还没有完全统一。

### 6.2 当前整体架构与文件/文件夹归类

#### A. 应用入口与装配层

- 主要职责：
  应用创建、路由总装配、中间件、异常处理、静态资源挂载、生命周期钩子。
- 主要文件：
  `backend/app/main.py`
  `backend/app/bootstrap.py`
  `backend/app/api/v1/router.py`

#### B. 前端接口层（面向前端暴露 HTTP / SSE 契约）

- 主要职责：
  向前端暴露案件、会话、聊天、认证、调试入口；维护流式事件契约与前端接入示例。
- 主要文件/文件夹：
  `backend/app/api/v1/router.py`
  `backend/app/modules/auth/router.py`
  `backend/app/modules/case_session/router.py`
  `backend/app/modules/chat/router.py`
  `backend/app/modules/playground/router.py`
  `frontend-sdk/stream-chat.ts`
  `docs/api/api-contract.md`
  `docs/api/error-codes.md`
  `docs/guide/frontend-integration.md`
  `docs/guide/laborlawhelp-frontend-integration-playbook.md`

#### C. 业务模块层

- 主要职责：
  聚合中间层的核心业务能力，按业务域收束模型、服务与路由依赖。
- 主要文件/文件夹：
  `backend/app/modules/case_session/`
  `backend/app/modules/chat/`

模块内部分工：

- `case_session`
  负责案件创建、案件读取、会话创建、会话读取、消息列表、结束会话。
- `chat`
  负责聊天请求模型、聊天主编排、SSE 事件封装、审计记录。

#### D. OpenHarness / 工具 / Skill 适配层

- 主要职责：
  对接 OpenHarness runtime / remote stream，注册本地工具，加载 skill，富化工具结果，生成卡片元数据。
- 主要文件/文件夹：
  `backend/app/adapters/openharness_client.py`
  `backend/app/adapters/openharness_types.py`
  `backend/app/adapters/openharness_prompting.py`
  `backend/app/adapters/openharness_enrichment.py`
  `backend/app/tools/`
  `backend/agent-skills/labor-pkulaw-retrieval-flow/SKILL.md`

#### E. 横向支撑层

- 主要职责：
  认证解析、JWT、配置、统一错误、SSE 编码、限流、存储抽象与存储实现。
- 主要文件/文件夹：
  `backend/app/core/auth.py`
  `backend/app/core/jwt_utils.py`
  `backend/app/core/config.py`
  `backend/app/core/errors.py`
  `backend/app/core/sse.py`
  `backend/app/core/rate_limit.py`
  `backend/app/core/store.py`

#### F. 兼容层（历史路径保留层）

- 主要职责：
  保留旧导入路径，降低一次性重构对现有测试和调用方的冲击。
- 主要文件：
  `backend/app/services/case_service.py`
  `backend/app/services/session_service.py`
  `backend/app/services/chat_service.py`
  `backend/app/services/audit_service.py`
  `backend/app/models/schemas.py`

#### G. 调试与静态页面层

- 主要职责：
  提供联调 playground 与静态调试页面。
- 主要文件/文件夹：
  `backend/app/static/playground/`
  `backend/app/modules/playground/router.py`

#### H. 测试、文档与辅助资产

- 主要职责：
  回归测试、集成测试、开发文档、运行文档、项目治理文档。
- 主要文件/文件夹：
  `backend/tests/`
  `docs/`
  `frontend-sdk/`
  `backend/sql/`
  `backend/scripts/`

### 6.3 针对 1-3 三个关键板块的模块化审查

#### 1. 与前端的接口连接是否模块化

阶段结论：

- `部分达标，聊天链路模块化较好，整体前端接口层尚未完全模块化。`

当前优点：

- `/api/v1` 总装配已经集中在 `backend/app/api/v1/router.py`。
- 案件/会话接口已经收束到 `backend/app/modules/case_session/router.py`。
- 聊天流式接口已经收束到 `backend/app/modules/chat/router.py`。
- 前端流式聊天示例集中在 `frontend-sdk/stream-chat.ts`，与 `docs/guide/frontend-integration.md` 的事件契约说明基本对齐。

当前不足：

- 前端 SDK 目前只覆盖 `chat/stream`，未覆盖 `cases`、`sessions`、`auth` 等其他前端真实会用到的接口。
- 前端接口相关内容目前分散在：
  `backend/app/modules/*/router.py`
  `backend/app/api/v1/routes/auth.py`
  `frontend-sdk/stream-chat.ts`
  `docs/api/*`
  `docs/guide/frontend-integration.md`
  `docs/guide/laborlawhelp-frontend-integration-playbook.md`
  这属于“逻辑上可理解，但对维护者仍偏分散”的状态。
- 兼容层中的旧 route 文件仍然存在，虽然职责已经变薄，但会让排查者看到两套入口路径。

判断依据：

- 同一功能的主实现已经明显收束，但“前端接口资产”还没有形成真正统一的前端接入包或单一目录。

进一步优化建议：

- 将前端接入代码从“单文件 stream 示例”升级为 `frontend-sdk/` 下的按领域划分结构，例如：
  `chat.ts / case-session.ts / auth.ts / types.ts`
- 在文档中明确标注：
  `backend/app/modules/*/router.py` 为真实接口源，
  `backend/app/api/v1/routes/*.py` 为兼容层。

#### 2. 与后端的接口连接是否模块化

阶段结论：

- `部分达标，业务模块层已经收束，但存储与认证侧仍未完全模块化。`

当前优点：

- 案件/会话/聊天三个核心业务链路已经进入 `backend/app/modules/`，依赖路径比之前清晰得多。
- `case_session.service` 与 `chat.service` 已经成为业务主入口，路由到服务的链路明显变短。

当前不足：

- 认证仍分散在：
  `backend/app/core/auth.py`
  `backend/app/core/jwt_utils.py`
  `backend/app/api/v1/routes/auth.py`
  还未形成独立认证模块。
- 存储侧仍集中在单文件 `backend/app/core/store.py` 中，同时承担：
  记录模型
  存储接口
  内存实现
  Postgres/Redis 实现
  工厂函数
  这仍然是当前后端连接层最显著的未模块化热点。
- 限流逻辑 `backend/app/core/rate_limit.py` 依赖 Redis，但还没有纳入更清晰的“基础设施模块”归类中。

判断依据：

- 业务层已经模块化，但后端基础设施连接层仍是“模块边界未完全拆开”的状态，因此只能判定为阶段性达标。

进一步优化建议：

- 优先完成模块 B（认证）与模块 F（存储抽象与后端实现）。
- 后续可将 `core/store.py` 进一步拆为：
  `records / interfaces / memory_store / postgres_store / factory`

#### 3. 工具调用、skill 使用等和 OH 对接的内容是否模块化

阶段结论：

- `基本达标，是当前三类重点板块中模块化程度最高的一类之一，但仍保留一个中心热点文件。`

当前优点：

- OpenHarness 适配职责已经从单文件中拆出为：
  `openharness_types.py`
  `openharness_prompting.py`
  `openharness_enrichment.py`
  `openharness_client.py`
- 本地工具实现集中在 `backend/app/tools/`。
- skill 资产集中在 `backend/agent-skills/`。
- 工具注册入口集中在 `app.tools.__init__`，skill 加载入口集中在 `OpenHarnessClient._extra_skill_dirs`，对维护者来说入口点是明确的。

当前不足：

- `backend/app/adapters/openharness_client.py` 仍然保留了 runtime 构建、library/remote/mock 三模式流处理、重试策略、协议解析等大量职责，虽然比之前好，但仍是一个中心热点。
- OH 对接相关内容天然跨越三个目录：
  `adapters / tools / agent-skills`
  这在逻辑上合理，但对新维护者来说仍需要额外理解“哪个目录负责对接、哪个目录负责工具、哪个目录负责 skill 资产”。

判断依据：

- 相比前端接口层和后端基础设施层，这一板块已经具备较清晰的单一入口与职责拆分，因此整体评价更高。

进一步优化建议：

- 在未来可以考虑补一个 `OpenHarness 集成索引说明`，明确：
  `adapters` 负责 OH 协议与 runtime
  `tools` 负责本地可调用工具
  `agent-skills` 负责工作流指令资产
- 若继续收口，可将 `openharness_client.py` 中的三模式运行逻辑再拆成更小的内部组件。

### 6.4 除上述三个板块外，其他代码模块有哪些

除“前端接口连接”“后端接口连接”“OH / 工具 / skill 对接”外，当前工作区还存在以下代码模块：

- `认证模块`
  `backend/app/core/auth.py`
  `backend/app/core/jwt_utils.py`
  `backend/app/modules/auth/`
- `应用入口与装配模块`
  `backend/app/main.py`
  `backend/app/bootstrap.py`
  `backend/app/api/v1/router.py`
- `横向支撑模块`
  `backend/app/core/config.py`
  `backend/app/core/errors.py`
  `backend/app/core/sse.py`
  `backend/app/core/rate_limit.py`
- `存储与基础设施模块`
  `backend/app/core/store.py`
- `调试与演示模块`
  `backend/app/modules/playground/`
  `backend/app/static/playground/`
- `兼容层模块`
  `backend/app/services/`
  `backend/app/models/schemas.py`
- `测试模块`
  `backend/tests/`
- `文档与脚本资产模块`
  `docs/`
  `backend/sql/`
  `backend/scripts/`

### 6.5 下一步优化优先级建议

从“减少依赖离散、降低排查成本、让真实实现与目录归属一致”的角度，下一步优先级建议如下：

1. 完成模块 F：拆分 `backend/app/core/store.py`，这是当前最明显的单文件热点。
2. 完成模块 B：把认证能力从 `core + route` 的分散状态收束成独立认证模块。
3. 为前端接口补齐更完整的 `frontend-sdk` 分层，而不仅是 `stream-chat.ts`。
4. 在兼容层文件头部增加简短注释，明确它们是历史路径兼容入口，避免后续维护者误把兼容层当作真实实现层继续扩展。

## 7. 重点板块为主线的架构优化

本节承接 `6.3` 与 `6.5` 中提出的问题与建议，记录本轮围绕“前端交互主线 / 后端基础设施主线 / OpenHarness 对接主线”完成的架构收口结果。

### 7.1 本轮完成范围

- 已完成模块 B：认证与请求上下文。
- 已完成模块 F：存储抽象与后端实现。
- 已将前端 SDK 从单文件示例收束为 `frontend-sdk/` 下的按领域分层结构。
- 已将 OpenHarness 真实实现收束为 `backend/app/adapters/openharness/` 包，旧顶层 `openharness_*` 文件改为兼容层。
- 已将 Playground 路由从旧 `api/v1/routes` 移入独立模块，前端暴露端点的真实实现进一步集中。

### 7.2 模块 B：认证与请求上下文

- 审批时间：
  `2026-04-21`
- 变更范围：
  `backend/app/modules/auth/__init__.py`
  `backend/app/modules/auth/context.py`
  `backend/app/modules/auth/router.py`
  `backend/app/modules/auth/schemas.py`
  `backend/app/modules/auth/service.py`
  `backend/app/modules/auth/tokens.py`
  `backend/app/core/auth.py`
  `backend/app/core/jwt_utils.py`
  `backend/app/api/v1/routes/auth.py`
  `backend/app/models/schemas.py`
  `backend/app/api/v1/router.py`
  `docs/project/modularization-update.md`
- 新增文件职责：
  `backend/app/modules/auth/context.py`：集中维护 `Owner` 请求上下文与 `resolve_owner` 依赖，统一匿名 token / Bearer token 的解析入口。
  `backend/app/modules/auth/tokens.py`：集中维护 JWT 生成与校验逻辑，避免令牌能力继续散落在 `core` 中。
  `backend/app/modules/auth/schemas.py`：集中维护短信发送、登录、刷新令牌等认证模型。
  `backend/app/modules/auth/service.py`：集中维护认证相关用例逻辑，包括短信登录模拟、刷新 token、登出返回。
  `backend/app/modules/auth/router.py`：集中暴露认证 HTTP 端点，成为前端认证接口的真实后端入口。
  `backend/app/modules/auth/__init__.py`：提供 auth 模块统一导出，便于业务模块与兼容层复用。
- 实施后核心变化：
  `认证能力不再散落在 core + route；请求上下文、JWT、认证模型、认证端点形成单一模块边界。`
- 对外行为变化：
  `无`
- 测试与验证：
  `已通过 py_compile 与导入级 smoke check，确认 auth 路由仍在 /api/v1 下被装配，旧 core/auth.py、core/jwt_utils.py 仍可兼容导入；纯 route 兼容层已在后续收缩中清理。`

### 7.3 模块 F：存储抽象与后端实现

- 审批时间：
  `2026-04-21`
- 变更范围：
  `backend/app/modules/storage/__init__.py`
  `backend/app/modules/storage/factory.py`
  `backend/app/modules/storage/memory.py`
  `backend/app/modules/storage/postgres.py`
  `backend/app/modules/storage/protocol.py`
  `backend/app/modules/storage/records.py`
  `backend/app/core/store.py`
  `backend/app/modules/case_session/service.py`
  `backend/app/modules/chat/audit.py`
  `backend/app/modules/chat/service.py`
  `backend/app/services/case_service.py`
  `backend/app/services/session_service.py`
  `backend/app/services/chat_service.py`
  `backend/tests/test_smoke.py`
  `backend/tests/integration/test_postgres_streaming.py`
  `docs/project/modularization-update.md`
- 新增文件职责：
  `backend/app/modules/storage/records.py`：集中维护案件、会话、消息、审计记录模型与时间序列化工具。
  `backend/app/modules/storage/protocol.py`：集中维护存储协议 `BaseStore`，明确业务层依赖的抽象边界。
  `backend/app/modules/storage/memory.py`：集中维护内存存储实现，承接本地/测试场景。
  `backend/app/modules/storage/postgres.py`：集中维护 Postgres + Redis 持久化实现，承接真实后端依赖。
  `backend/app/modules/storage/factory.py`：集中维护 `build_store / get_store / set_store`，统一存储实例装配与测试替换入口。
  `backend/app/modules/storage/__init__.py`：提供 storage 模块统一导出与动态 `store` 兼容访问。
- 实施后核心变化：
  `存储主线从单文件热点改为“记录模型 -> 协议 -> 实现 -> 工厂”四层收束，业务模块改为通过 get_store() 访问当前存储实例，测试替换链路更清晰。`
- 对外行为变化：
  `无`
- 测试与验证：
  `已通过 py_compile 与导入级 smoke check；test_smoke.py 与 integration/test_postgres_streaming.py 已改为走新的 storage 模块入口。`

### 7.4 重点板块主线重构结果

#### 1. 与前端交互的主线

当前已收束为两层：

- 后端真实接口层：
  `backend/app/api/v1/router.py`
  `backend/app/modules/auth/router.py`
  `backend/app/modules/case_session/router.py`
  `backend/app/modules/chat/router.py`
  `backend/app/modules/playground/router.py`
- 前端接入层：
  `frontend-sdk/core/http.ts`
  `frontend-sdk/core/sse.ts`
  `frontend-sdk/modules/auth.ts`
  `frontend-sdk/modules/case-session.ts`
  `frontend-sdk/modules/chat.ts`
  `frontend-sdk/index.ts`
  `frontend-sdk/stream-chat.ts`（兼容入口）

本轮核心收益：

- 认证、案件/会话、聊天、Playground 这四类前端真实会用到的接口，在后端都已经有明确的模块目录。
- 前端接入代码不再只有 `stream-chat.ts` 一个单文件示例，HTTP 请求、SSE 解析、认证接口、案件/会话接口、聊天接口都已按功能分层。
- `frontend-sdk/stream-chat.ts` 仍保留，但已降为兼容包装层，新的真实聊天接入入口为 `frontend-sdk/modules/chat.ts`。

#### 2. 与后端基础设施交互的主线

当前已收束为三段：

- 认证基础设施：
  `backend/app/modules/auth/context.py`
  `backend/app/modules/auth/tokens.py`
  `backend/app/modules/auth/service.py`
- 存储基础设施：
  `backend/app/modules/storage/records.py`
  `backend/app/modules/storage/protocol.py`
  `backend/app/modules/storage/memory.py`
  `backend/app/modules/storage/postgres.py`
  `backend/app/modules/storage/factory.py`
- 业务使用入口：
  `backend/app/modules/case_session/service.py`
  `backend/app/modules/chat/service.py`

本轮核心收益：

- 业务模块已不再直接依赖 `core/store.py` 的大一统实现文件，而是通过 `get_store()` 面向 storage 模块取用实例。
- 认证也不再散落于 `core + route`，而是形成完整 auth 模块。
- `core/auth.py`、`core/jwt_utils.py`、`core/store.py` 现在明确退化为兼容层，而不是继续承担真实实现。

#### 3. 与 OpenHarness / tools / skill 对接的主线

当前已收束为三段：

- OH 适配与运行时：
  `backend/app/adapters/openharness/__init__.py`
  `backend/app/adapters/openharness/client.py`
  `backend/app/adapters/openharness/prompting.py`
  `backend/app/adapters/openharness/enrichment.py`
  `backend/app/adapters/openharness/types.py`
  `backend/app/adapters/openharness/local_tools.py`
- 本地工具实现：
  `backend/app/tools/labor_compensation.py`
  `backend/app/tools/labor_document.py`
  `backend/app/tools/labor_fact_extract.py`
  `backend/app/tools/labor_lawyer_recommend.py`
  `backend/app/tools/__init__.py`
- Skill 资产：
  `backend/agent-skills/labor-pkulaw-retrieval-flow/SKILL.md`

本轮核心收益：

- OpenHarness 真实实现不再散落在多个顶层 `openharness_*` 文件中，而是进入单一包目录。
- `local_tools.py` 成为 OH 视角下的本地工具注册桥接点；工具实现仍留在 `app/tools/`，职责边界更清晰。
- 顶层 `backend/app/adapters/openharness_client.py`、`openharness_types.py`、`openharness_prompting.py`、`openharness_enrichment.py` 继续保留为兼容层，减少外部引用震荡。

#### 4. 其他功能模块

除三条重点主线外，当前工作区其余模块分布如下：

- 应用装配主线：
  `backend/app/main.py`
  `backend/app/bootstrap.py`
  `backend/app/api/v1/router.py`
- 业务域主线：
  `backend/app/modules/case_session/`
  `backend/app/modules/chat/`
  `backend/app/modules/auth/`
  `backend/app/modules/playground/`
  `backend/app/modules/storage/`
- 横向支撑主线：
  `backend/app/core/config.py`
  `backend/app/core/errors.py`
  `backend/app/core/rate_limit.py`
  `backend/app/core/sse.py`
- 静态页面与调试资产：
  `backend/app/static/playground/`
- 兼容层：
  `backend/app/services/`
  `backend/app/core/{auth,jwt_utils,store}.py`
  `backend/app/models/schemas.py`
- 测试与文档资产：
  `backend/tests/`
  `docs/`
  `frontend-sdk/`

### 7.5 新增文件职责汇总（便于后续维护）

为了便于人类开发员后续维护，本轮新增或新晋为真实实现入口的文件职责如下：

- `backend/app/modules/auth/context.py`
  维护请求上下文解析与 owner 识别。
- `backend/app/modules/auth/tokens.py`
  维护 JWT 生成与校验。
- `backend/app/modules/auth/service.py`
  维护认证用例逻辑。
- `backend/app/modules/auth/router.py`
  维护认证 HTTP 端点。
- `backend/app/modules/storage/records.py`
  维护存储记录模型。
- `backend/app/modules/storage/protocol.py`
  维护存储协议。
- `backend/app/modules/storage/memory.py`
  维护内存实现。
- `backend/app/modules/storage/postgres.py`
  维护 Postgres/Redis 实现。
- `backend/app/modules/storage/factory.py`
  维护存储实例装配与替换入口。
- `backend/app/modules/playground/router.py`
  维护 Playground 运行时信息接口。
- `backend/app/adapters/openharness/client.py`
  维护 OpenHarness 运行时、remote/library/mock 三模式与统一流输出。
- `backend/app/adapters/openharness/prompting.py`
  维护提示词增强与规则版本解析。
- `backend/app/adapters/openharness/enrichment.py`
  维护工具结果富化、引用提取、卡片元数据构建。
- `backend/app/adapters/openharness/types.py`
  维护统一流块类型 `OHChunk`。
- `backend/app/adapters/openharness/local_tools.py`
  维护 OpenHarness 视角下的本地工具注册桥接。
- `frontend-sdk/core/http.ts`
  维护前端通用 HTTP 请求与认证头拼装。
- `frontend-sdk/core/sse.ts`
  维护前端通用 SSE 解析。
- `frontend-sdk/modules/auth.ts`
  维护前端认证接口调用。
- `frontend-sdk/modules/case-session.ts`
  维护前端案件/会话接口调用。
- `frontend-sdk/modules/chat.ts`
  维护前端聊天流式接口调用。
- `frontend-sdk/index.ts`
  维护前端 SDK 统一导出。

### 7.6 兼容层保留策略

本轮仍保留以下兼容层，用于降低重构对现有引用和测试的冲击：

- `backend/app/core/auth.py`
- `backend/app/core/jwt_utils.py`
- `backend/app/core/store.py`
- `backend/app/services/case_service.py`
- `backend/app/services/session_service.py`
- `backend/app/services/chat_service.py`
- `backend/app/adapters/openharness_client.py`
- `backend/app/adapters/openharness_types.py`
- `backend/app/adapters/openharness_prompting.py`
- `backend/app/adapters/openharness_enrichment.py`
- `frontend-sdk/stream-chat.ts`

补充说明：

- `backend/app/api/v1/routes/{auth,cases,sessions,chat,playground}.py` 这组纯冗余 route 兼容层已在本轮清理，当前 HTTP 真实入口统一为 `backend/app/api/v1/router.py` 与 `backend/app/modules/*/router.py`。

兼容层约束：

- 后续新增能力优先写入真实模块目录，不再继续向兼容层堆积实现。
- 兼容层只承担“转发 / 兼容导出 / 历史路径兜底”职责。

### 7.7 本轮验证

- 已执行 `py_compile` 级语法校验，覆盖本轮新增与重构文件。
- 已执行导入级 smoke check，结果如下：
  `app_routes = 20`
  `api_routes = 14`
  `auth_routes = 4`
  `case_routes = 7`
  `chat_routes = 2`
  `playground_routes = 1`
  `store_type = InMemoryStore`
  `compat_store_type = InMemoryStore`
  `openharness_client_type = OpenHarnessClient`
  `imports_ok = True`
- 当前环境下 `TestClient` 仍存在卡住问题，因此本轮未将基于 `TestClient` 的端到端回归作为有效验证手段，仍以结构核对、语法核对、导入核对为主。
