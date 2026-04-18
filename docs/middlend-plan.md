---

### 智裁中间件设计文档 v2.2：生产级 LLM 应用网关

#### 0. 文档目的与本版裁决

本版用于将当前前端工程与中间件设计对齐，重点解决以下冲突：

1. 前端当前为本地规则驱动，中间件目标为服务端智能编排。
2. 前端当前无真实 API 链路，中间件需定义可直接实现的契约顺序。
3. 认证、会话模型、SSE 解析方式需要先裁决再开发。

**本版已确认裁决：**

- 认证采用阶段化：一期游客可用，二期切换 JWT 强制认证。
- 聊天通信固定为 POST + text/event-stream（前端用 ReadableStream 解析）。
- 会话模型立即采用 case/session 双层。
- 本地规则引擎仅保留回退开关，默认关闭。
- HR 风险接口化进入第二期，不阻塞咨询主链路。

**0.1 前端现状与中间件目标对齐矩阵**

| 主题 | 前端当前现状 | 中间件目标 | 改造动作 |
| :--- | :--- | :--- | :--- |
| 聊天通信 | 本地模拟打字机，无真实后端流 | POST + SSE 实时流 | 将咨询页改为 fetch + ReadableStream 解析 |
| 会话模型 | 前端单体状态，无 case/session ID | case/session 双层模型 | 在状态层新增 case_id/session_id 与会话状态 |
| 业务计算 | 前端本地规则直接计算 | OpenHarness 驱动结果生成 | 本地规则仅保留回退开关，默认关闭 |
| 认证策略 | 当前未接入统一登录 | 一期游客，二期 JWT | 先接入匿名会话令牌，再平滑切换登录态 |
| HR 风险 | 页面本地规则计算 | 服务端接口化 + 审计 | 列入二期里程碑，不阻塞咨询主链路 |

---

#### 1. 架构原则与职责划分

| 层级 | 职责 | 不负责 |
| :--- | :--- | :--- |
| **前端 (Next.js)** | 用户交互、会话展示、消息发送、SSE 接收与渲染、会话状态管理。 | 业务规则判定、金额计算、文书生成。 |
| **中间件 (FastAPI)** | 会话生命周期管理、请求/响应协议标准化、OpenHarness 适配、SSE 流式代理、审计日志、阶段化认证治理。 | 执行具体法律推理或法条检索。 |
| **OpenHarness Runtime** | 多轮对话管理、意图理解、技能调度、MCP 工具调用、生成最终回答。 | 直接管理用户登录态、数据库事务、会话并发锁。 |

**关键原则：**

- 中间件是 OpenHarness 的代理与安全边界，不是业务规则容器。
- 智能行为由 OpenHarness 内 skill/tool 完成，中间件负责治理与编排。
- 前端只通过标准 HTTP/SSE 协议通信，不承载法律口径主逻辑。

---

#### 2. 核心数据模型

**2.1 PostgreSQL（支持游客阶段 + 登录阶段）**

```sql
-- 用户表（登录阶段使用）
CREATE TABLE users (
    id UUID PRIMARY KEY,
    phone VARCHAR(20) UNIQUE,
    wechat_unionid VARCHAR(64) UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 案件表（一期允许匿名案件，二期要求绑定 user_id）
CREATE TABLE cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    anonymous_id VARCHAR(64),
    owner_type VARCHAR(20) NOT NULL DEFAULT 'anonymous', -- anonymous/user
    title VARCHAR(200) DEFAULT '未命名案件',
    region_code VARCHAR(20) DEFAULT 'xian',
    status VARCHAR(20) DEFAULT 'active', -- active/archived
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 会话表（沿用 case/session 双层）
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id),
    user_id UUID REFERENCES users(id),
    anonymous_id VARCHAR(64),
    openharness_session_id VARCHAR(128),
    status VARCHAR(20) DEFAULT 'active', -- active/ended/expired
    message_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW()
);

-- 审计日志表（合规必需）
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID NOT NULL,
    user_id UUID,
    anonymous_id VARCHAR(64),
    session_id UUID,
    event_type VARCHAR(50), -- api_request/oh_tool_call/oh_final
    request_payload JSONB,
    response_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**2.2 Redis 缓存结构**

| Key | 类型 | 用途 | TTL |
| :--- | :--- | :--- | :--- |
| `owner:{owner_id}:sessions` | Set | 拥有者（user 或 anonymous）活跃会话列表 | - |
| `session:{session_id}:lock` | String | 会话级并发锁（防消息重叠） | 30s |
| `session:{session_id}:stream:seq` | String | SSE 流消息序号 | 会话生命周期 |
| `rate:owner:{owner_id}:minute` | String | 限流计数器 | 60s |
| `jwt:refresh:{user_id}:{jti}` | String | Refresh Token 黑名单 | 7d |

---

#### 3. API 接口设计（按前端落地顺序）

统一前缀：`/api/v1`

##### 3.1 认证与会话准入策略（阶段化）

| 阶段 | 准入方式 | 请求要求 |
| :--- | :--- | :--- |
| 一期（当前） | 游客模式 | 必须携带 `X-Anonymous-Token` 或由后端首呼签发 |
| 二期（目标） | 登录模式 | 必须携带 `Authorization: Bearer <access_token>` |

说明：一期先打通咨询主链路；二期切换 JWT 强制认证时，保留游客会话迁移脚本。

##### 3.2 案件与会话管理接口（先于聊天）

| 端点 | 方法 | 描述 |
| :--- | :--- | :--- |
| `/cases` | POST | 创建案件（owner_type = anonymous/user） |
| `/cases` | GET | 获取当前拥有者案件列表 |
| `/cases/{case_id}` | GET | 获取案件详情 |
| `/cases/{case_id}/sessions` | POST | 为案件创建会话并返回 session_id |
| `/cases/{case_id}/sessions` | GET | 获取案件下会话列表 |
| `/sessions/{session_id}/messages` | GET | 获取会话历史消息（分页） |
| `/sessions/{session_id}/end` | PATCH | 主动结束会话 |

##### 3.3 核心聊天接口（固定 POST + SSE）

- 端点：`POST /sessions/{session_id}/chat`
- Content-Type：`application/json`
- Response：`text/event-stream`
- 前端实现：fetch + ReadableStream + SSE framing（不采用 EventSource GET）

请求体：

```json
{
  "message": "我在西安一家科技公司工作两年，昨天被口头辞退。月薪8000。",
  "attachments": [
    {
      "id": "att_01JS9WAA2X8H4W8KQ2Z7N6H8PE",
      "name": "聊天记录截图.png",
      "url": "https://cdn.example.com/...",
      "mime_type": "image/png"
    }
  ],
  "client_seq": 12
}
```

SSE 事件定义：

| 事件类型 | 数据结构 | 描述 |
| :--- | :--- | :--- |
| `message_start` | `{"message_id":"msg_xxx"}` | 新助手消息开始 |
| `content_delta` | `{"delta":"...","seq":13}` | 增量文本（含序号） |
| `tool_call` | `{"tool_name":"...","args":{...}}` | 工具调用开始 |
| `tool_result` | `{"tool_name":"...","result_summary":"..."}` | 工具调用结束 |
| `final` | `{"message_id":"...","summary":"...","references":[]}` | 结构化结果 |
| `message_end` | `{"message_id":"..."}` | 当前消息结束 |
| `error` | `{"code":500,"message":"..."}` | 流内错误 |

##### 3.4 辅助查询接口（前端侧栏与下载）

| 端点 | 方法 | 描述 |
| :--- | :--- | :--- |
| `/sessions/{session_id}/summary` | GET | 获取会话结构化摘要 |
| `/sessions/{session_id}/document` | GET | 下载文书草稿（DOCX/PDF） |
| `/cases/{case_id}/triage` | GET | 获取案件分流结果 |

##### 3.5 登录接口（二期启用）

| 端点 | 方法 | 描述 |
| :--- | :--- | :--- |
| `/auth/sms/send` | POST | 发送手机验证码 |
| `/auth/sms/login` | POST | 验证码登录，返回 access_token / refresh_token |
| `/auth/refresh` | POST | 刷新 Token |
| `/auth/logout` | POST | 登出，撤销 Refresh Token |

---

#### 4. 中间件核心流程

**4.1 请求处理管道（一期游客 + 二期登录统一骨架）**

```python
@router.post("/sessions/{session_id}/chat")
async def chat_stream(session_id: UUID, request: ChatRequest, owner: Owner = Depends(resolve_owner)):
    # 1. 权限校验：会话必须归属当前 owner（anonymous/user）
    session = await get_session_with_owner(session_id, owner)

    # 2. 限流检查（按 owner 维度）
    await check_rate_limit(owner.id)

    # 3. 获取分布式锁，防止同一会话并发请求
    async with redis.lock(f"session:{session_id}:lock", timeout=30):
        await save_user_message(session_id, request.message, request.attachments)

        async def event_generator():
            assistant_msg_id = str(uuid.uuid4())
            yield sse_event("message_start", {"message_id": assistant_msg_id})

            full_response = ""
            tool_calls = []

            oh_input = {
                "prompt": request.message,
                "session_id": session.openharness_session_id,
                "user_context": {
                    "owner_type": owner.type,
                    "owner_id": owner.id,
                    "region": session.region_code,
                    "attachments": [a.dict() for a in request.attachments]
                },
                "output_format": "stream"
            }

            async with openharness_client.stream_run(oh_input) as oh_stream:
                async for chunk in oh_stream:
                    if chunk.type == "text":
                        full_response += chunk.content
                        seq = await incr_stream_seq(session_id)
                        yield sse_event("content_delta", {"delta": chunk.content, "seq": seq})
                    elif chunk.type == "tool_call":
                        tool_calls.append(chunk.tool_name)
                        yield sse_event("tool_call", {"tool_name": chunk.tool_name, "args": chunk.args})
                    elif chunk.type == "tool_result":
                        yield sse_event("tool_result", {"tool_name": chunk.tool_name})
                    elif chunk.type == "final":
                        await save_assistant_message(session_id, assistant_msg_id, full_response, chunk.metadata)
                        await update_session_stats(session_id)
                        yield sse_event("final", {
                            "message_id": assistant_msg_id,
                            "summary": chunk.metadata.get("summary"),
                            "references": chunk.metadata.get("references", []),
                            "rule_version": chunk.metadata.get("rule_version")
                        })
                        break

            yield sse_event("message_end", {"message_id": assistant_msg_id})
            await audit_log(session_id, owner, full_response, tool_calls)

        return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**4.2 OpenHarness 集成配置**

```env
OH_BASE_URL=http://localhost:8080
OH_API_KEY=sk-xxxx
OH_DEFAULT_WORKFLOW=labor_consultation
APP_ENABLE_LOCAL_RULE_FALLBACK=false
```

说明：`APP_ENABLE_LOCAL_RULE_FALLBACK` 为迁移期兜底开关，默认 false，仅在中间件不可用时临时启用。

**4.3 回退策略（迁移期临时）**

1. 首选中间件 + OpenHarness。
2. 当 OpenHarness 或依赖短时不可用且开关启用时，回退到本地规则引擎。
3. 回退路径必须记录审计日志并标注 `fallback=true`，用于后续补偿校验。

---

#### 5. 错误处理规范

| HTTP 状态码 | 错误码 | 说明 | 前端处理建议 |
| :--- | :--- | :--- | :--- |
| 400 | `BAD_REQUEST` | 请求参数错误 | 提示用户重新输入 |
| 401 | `UNAUTHORIZED` | Token 无效或过期（二期） | 引导登录 |
| 403 | `FORBIDDEN` | 无权访问该会话 | 返回案件列表 |
| 409 | `SESSION_LOCKED` | 同一会话并发消息冲突 | 提示稍后重试 |
| 410 | `ANONYMOUS_SESSION_EXPIRED` | 游客会话过期 | 引导创建新会话 |
| 429 | `RATE_LIMITED` | 请求过于频繁 | 自动退避重试 |
| 500 | `OH_SERVICE_ERROR` | OpenHarness 执行异常 | 显示友好错误并建议重试 |
| 503 | `SERVICE_UNAVAILABLE` | 依赖服务不可用 | 提示部分功能受限 |

SSE 流内错误事件示例：

```text
event: error
data: {"code": 503, "message": "服务暂时不可用，您可稍后重试。", "retryable": true}
```

---

#### 6. 会话生命周期管理

**6.1 会话创建（强制先创建后聊天）**

1. 前端先调用 `POST /cases`。
2. 再调用 `POST /cases/{case_id}/sessions` 获取 `session_id`。
3. 最后调用 `POST /sessions/{session_id}/chat`。

**6.2 会话恢复**

- 前端继续使用既有 `session_id`。
- 中间件读取 `openharness_session_id` 恢复上下文。
- 若会话无效，返回 `ANONYMOUS_SESSION_EXPIRED` 或 `FORBIDDEN`。

**6.3 会话过期与结束**

- `last_active_at` 超过 24 小时自动标记 `expired`。
- 用户主动结束时调用 `PATCH /sessions/{session_id}/end`。

**6.4 并发控制与断流恢复**

- 使用 `session:{session_id}:lock` 保证会话串行处理。
- 前端可携带 `client_seq`，中间件按 `seq` 保障重连后的顺序一致性。

---

#### 7. 部署与运维考量

**7.1 环境变量**

```env
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
JWT_SECRET_KEY=...
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
OH_BASE_URL=...
OH_API_KEY=...
APP_ENABLE_LOCAL_RULE_FALLBACK=false
```

**7.2 监控指标**

- SSE 连接数、平均响应时间、OpenHarness 调用成功率。
- 会话创建数、消息发送量、游客到登录转化率。
- 回退开关触发次数、回退路径占比。

**7.3 日志格式**

结构化 JSON 日志字段建议：`trace_id`、`owner_type`、`owner_id`、`session_id`、`event`、`duration_ms`、`fallback`。

---

#### 8. 前端对接指南（与当前仓库对齐）

1. 首屏初始化：先创建 case，再创建 session，写入前端状态。
2. 聊天发送：始终使用 POST，响应流按 SSE 帧解析。
3. UI 更新：
   - `content_delta` 按 seq 增量拼接。
   - `tool_call`/`tool_result` 用于状态提示。
   - `final` 用于更新摘要和引用侧栏。
4. 回退机制：仅在中间件不可用且后端返回可回退信号时启用本地规则路径。
5. 二期登录：接入 JWT 后保留原 case/session 模型，不重构会话主链路。

---

#### 9. 总结：满足关键要求

| 要求 | 实现方式 |
| :--- | :--- |
| 前端仅做展示 | 业务判定下沉到 OpenHarness，前端仅做输入输出与状态呈现。 |
| 通信标准稳定 | 固定 POST + SSE，避免双协议并存导致维护复杂度上升。 |
| 会话管理可演进 | 立即采用 case/session 双层，并支持游客到登录平滑迁移。 |
| 可直接开发 | API 契约顺序、错误码、生命周期与伪代码均可直接落地。 |

此文档作为后端、中间件、前端、算法团队的统一实现依据。