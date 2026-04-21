# laborlawhelp 前端对接改造指南（面向中间件 + OpenHarness）

## 1. 文档目的
本指南用于把 laborlawhelp 前端从“本地规则驱动”迁移为“中间件 SSE 驱动”，并保持当前 UI 交互体验不倒退。

目标读者：
- 前端开发（主）
- 联调开发（前后端协同）
- 测试同学（接口与流式验收）

---

## 2. 现状与目标

## 2.1 前端现状（来自 laborlawhelp 仓库）
当前 `consultation/page.tsx` 仍以本地函数为主链路：
- 通过 `getAssistantResponse()` 本地拼接回复。
- 通过 `pendingResponse + 打字机 effect` 模拟流式输出。
- 核心业务能力直接调用本地模块：
  - `src/lib/calculation.ts`
  - `src/lib/dialogue-flow.ts`
  - `src/lib/document-generator.ts`
  - `src/lib/case-triage.ts`

同时，状态集中在 `src/hooks/use-case-store.tsx`，但尚未承载中间件 case/session 双层会话状态。

## 2.2 迁移目标
将咨询主链路改为：
1. 先创建 case
2. 再创建 session
3. 最后调用 `POST /sessions/{session_id}/chat/stream` 消费 SSE

即：
- 前端负责输入、展示、状态机。
- 后端负责推理、工具调用、摘要、引用。
- 本地规则模块仅保留回退路径，默认关闭。

---

## 3. 对接边界与契约
本项目后端契约以以下文档为准：
- `docs/api/api-contract.md`
- `docs/api/error-codes.md`

关键接口顺序：
1. `POST /api/v1/cases`
2. `POST /api/v1/cases/{case_id}/sessions`
3. `POST /api/v1/sessions/{session_id}/chat`（SSE）

核心 SSE 事件：
- `message_start`
- `content_delta`
- `tool_call`
- `tool_result`
- `final`
- `message_end`
- `error`

---

## 4. 前端状态模型改造（必须）
建议在 `use-case-store.tsx` 新增会话域状态，不破坏现有案情状态。

## 4.1 建议新增状态
```ts
interface BackendSessionState {
  owner: {
    owner_type: 'anonymous' | 'user'
    anonymous_token?: string
    access_token?: string
    refresh_token?: string
  }
  case_id?: string
  session_id?: string
  session_status?: 'active' | 'ended' | 'expired'
  current_message_id?: string
  is_streaming: boolean
  last_seq: number
  last_error?: {
    code: string
    message: string
    retryable: boolean
  }
  final_payload?: {
    summary?: string
    references?: Array<{ title?: string; url?: string; snippet?: string }>
    rule_version?: string
  }
}
```

## 4.2 建议新增 action
```ts
setBackendOwner(...)
setCaseSession(caseId: string, sessionId: string)
startStreaming(messageId: string)
appendDelta(seq: number, delta: string)
setToolStatus(...)
setFinalPayload(...)
endStreaming()
setStreamError(...)
resetBackendSession()
```

---

## 5. 目录与模块拆分建议
为了避免继续把网络、状态、UI 全写在 `consultation/page.tsx`，建议最小拆分如下：

```text
src/
  features/
    consultation/
      api/
        client.ts                 # 通用 request 封装
        chat-stream.ts            # SSE 解析器
        endpoints.ts              # cases/sessions/chat 调用
      services/
        consultation-profile.ts   # 已有，继续保留
      adapters/
        sse-event-mapper.ts       # SSE 事件 -> store action
```

说明：
- `page.tsx` 只保留交互与渲染。
- API 调用与 SSE 解析下沉到 `features/consultation/api/*`。

---

## 6. 网络层实现建议

## 6.1 环境变量
新增并约定：
- `NEXT_PUBLIC_MIDDLEND_BASE_URL`

示例：
```env
NEXT_PUBLIC_MIDDLEND_BASE_URL=http://localhost:8000
```

不要暴露：
- JWT secret
- 服务端私钥
- OpenHarness key

## 6.2 通用请求封装
建议提供：
- 自动附加 `X-Anonymous-Token` 或 `Authorization`
- 统一错误解析（映射到 `code/message/retryable`）
- 自动透传 `X-Trace-Id`（如存在）

---

## 7. SSE 解析器（替换打字机主链路）

## 7.1 行为要求
1. 使用 `fetch + ReadableStream`。
2. 以 `\n\n` 分帧。
3. 使用 `TextDecoder(stream:true)` 处理 UTF-8 分片。
4. 忽略未知事件，确保向前兼容。
5. 对 `content_delta` 做 `seq` 单调校验。

## 7.2 建议骨架
```ts
export async function streamChat(
  args: {
    baseUrl: string
    sessionId: string
    payload: {
      message: string
      client_seq: number
      attachments?: Array<{ id: string; name: string; url: string; mime_type: string }>
    }
    headers: Record<string, string>
    onEvent: (event: string, data: any) => void
  }
) {
  const res = await fetch(`${args.baseUrl}/api/v1/sessions/${args.sessionId}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...args.headers,
    },
    body: JSON.stringify(args.payload),
  })

  if (!res.ok || !res.body) {
    throw new Error(`chat request failed: ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''

    for (const frame of frames) {
      const lines = frame.split('\n')
      const eventLine = lines.find((l) => l.startsWith('event:'))
      const dataLine = lines.find((l) => l.startsWith('data:'))
      if (!eventLine || !dataLine) continue

      const event = eventLine.slice(6).trim()
      const raw = dataLine.slice(5).trim()

      try {
        const data = JSON.parse(raw)
        args.onEvent(event, data)
      } catch {
        // 非法 data 跳过，不中断整流
      }
    }
  }
}
```

---

## 8. consultation 页面改造点（按函数级别）

## 8.1 需要替换的现有逻辑
在 laborlawhelp 前端中，以下逻辑应改为真实 SSE 驱动：
1. `getAssistantResponse()`
2. `pendingResponse` 打字机 `useEffect`
3. `handleSend` 中直接等待本地 response 的路径

## 8.2 新的发送流程
`handleSend` 应改为：
1. 前端先 `addMessage(user)`。
2. 若无 `case_id`：创建 case。
3. 若无 `session_id`：创建 session。
4. 发送 chat stream 请求。
5. 按事件更新 store 与 UI。

## 8.3 事件到 UI 的映射建议
- `message_start`：创建 assistant 占位消息。
- `content_delta`：追加文本到 assistant 消息。
- `tool_call`：显示“处理中”状态条。
- `tool_result`：更新工具状态摘要；若存在 `card_type/card_payload`，在消息流内渲染结构化结果卡。
- `final`：更新右侧会话总结、引用信息、规则版本。
- `message_end`：结束 loading，允许下次输入。
- `error`：展示错误提示与重试按钮。

---

## 9. 正式版主链路约束（中间件唯一）

正式版 consultation 页仅允许中间件主链路：

1. `handleSend` 必须走 cases/sessions/chat-stream 的 SSE 流程。
2. 禁止在生产路径中自动切回本地规则回复。
3. 本地模块（`calculation/dialogue-flow/document-generator/case-triage`）仅可用于离线开发验证，不得作为线上兜底输出。
4. 发生后端错误时，前端应展示可重试错误态，而不是拼接本地“回退结果”。

---

## 10. 错误码与前端交互策略
参考 `docs/api/error-codes.md`，建议统一处理：

- `BAD_REQUEST`：提示用户修正输入。
- `UNAUTHORIZED`：清理 token 并引导登录。
- `FORBIDDEN`：提示无权访问，返回案件选择。
- `SESSION_LOCKED`：提示稍后重试。
- `ANONYMOUS_SESSION_EXPIRED`：创建新会话并提示用户。
- `RATE_LIMITED`：退避重试（如 2s/4s）。
- `OH_SERVICE_ERROR`：友好错误文案 + 重试。

---

## 11. 分步实施计划（建议 3 次 PR）

### PR-1：打底能力
- 新增 API 客户端与 SSE 解析器。
- `use-case-store` 增加 case/session/stream 状态。
- 不改 UI 展示，仅接入调试日志。

### PR-2：主链路切换
- `consultation/page.tsx` 切换到真实 cases/sessions/chat/stream。
- 接入全部 SSE 事件映射。
- 保留本地模块仅用于离线开发验证，不进入生产自动回退路径。

### PR-3：体验收口
- 右侧摘要/引用/流程状态改为 `final` 事件驱动。
- 完善错误态与重试。
- 增加 e2e 场景与联调验收文档。

---

## 12. 联调验收清单

## 12.1 功能验收
1. 首次发送时自动完成 case + session 创建。
2. 聊天请求使用 POST 并成功消费 SSE。
3. `content_delta` 文本连续、无乱序。
4. `final` 信息可更新到会话摘要区域。
5. `message_end` 后输入框恢复可用。
6. `tool_result` 的 `card_*` 字段可驱动 UI 渲染要素卡/测算卡/文书卡/律师卡。

## 12.2 异常验收
1. 模拟 409：前端能提示并重试。
2. 模拟 410：前端能重建会话。
3. 模拟 429：前端有退避策略。
4. 模拟 500：前端展示友好错误，不崩溃。

## 12.3 质量验收
1. `pnpm build` 通过。
2. `pnpm lint` 通过。
3. `pnpm ts-check` 通过。

---

## 13. 与当前中间件文档的关系
建议阅读顺序：
1. `docs/api/api-contract.md`
2. `docs/api/error-codes.md`
3. `docs/guide/frontend-integration.md`
4. 本文档（仓库定制改造手册）

本文件关注“如何改 laborlawhelp 前端代码”；
`frontend-integration.md` 关注“通用前端对接原则”。
