# 前端接入指南（Next.js）

## 1. 接入生命周期（必须遵守）
1. `POST /cases`
2. `POST /cases/{case_id}/sessions`
3. `POST /sessions/{session_id}/chat/stream` 并解析流

在 `session` 创建完成前，不允许直接发起聊天。

## 2. 当前前端接入实现
仓库内已经提供一套以当前中间件为准的前端 SDK：

| 文件 | 作用 |
|---|---|
| `frontend-sdk/core/http.ts` | 统一构造匿名/JWT 请求头并发起 JSON 请求 |
| `frontend-sdk/core/sse.ts` | 解析中间件 SSE 帧 |
| `frontend-sdk/modules/auth.ts` | 认证端点调用 |
| `frontend-sdk/modules/case-session.ts` | 案件、会话、消息列表与结束会话调用 |
| `frontend-sdk/modules/chat.ts` | 聊天流式调用 |
| `frontend-sdk/stream-chat.ts` | 匿名场景的兼容包装入口 |

如果前端仓库直接对接 middlend，优先复用这套 SDK，而不是在业务页面里手写 `fetch + SSE` 主链路。

## 3. 客户端状态模型
| 状态 | 必需字段 |
|---|---|
| owner | `owner_type`、`anonymous_token` 或 JWT |
| case | `case_id`, `title`, `region_code` |
| session | `session_id`, `status`, `last_active_at` |
| stream | `current_message_id`, `trace_id`, `last_seq`, `is_streaming` |

## 4. 流解析要求
- 使用 `fetch` + `ReadableStream` 发起 `POST` 请求。
- 按 SSE 帧分隔符 `\n\n` 解析数据。
- 使用 `TextDecoder` 的 streaming 模式安全处理 UTF-8 分片。
- 按 `event` 类型分发事件。
- 保持 `seq` 单调递增；丢弃重复或更旧的 delta。
- 忽略未知事件和未知字段，以保持向前兼容。
- 仅把 `message_end` 视为单轮助手回复完成信号。

## 5. 事件契约与 UI 处理
| 事件 | 必需字段 | UI 处理 |
|---|---|---|
| `message_start` | `message_id`, `trace_id` | 创建待完成的助手消息气泡 |
| `content_delta` | `delta`, `seq`, `trace_id` | 按 `seq` 追加 token 文本 |
| `tool_call` | `tool_name`, `trace_id` | 显示“处理中”状态标记 |
| `tool_result` | `tool_name`, `result_summary`, `references`, `trace_id` | 更新状态，并在存在 `card_type/card_payload` 时渲染卡片 |
| `final` | `message_id`, `summary`, `references`, `rule_version`, `finish_reason`, `trace_id` | 填充摘要、引用和侧边栏数据 |
| `error` | `code`, `message`, `retryable`, `trace_id` | 标记可重试错误，同时保留已收到内容 |
| `message_end` | `message_id`, `trace_id` | 标记助手消息完成 |

`tool_result` 可选扩展字段：
- `card_type`
- `card_title`
- `card_payload`
- `card_actions`

## 6. 示例代码（TypeScript）

```ts
export async function streamChat(
  baseUrl: string,
  sessionId: string,
  payload: { message: string; client_seq: number; attachments?: Array<{ id: string; name: string; url: string; mime_type: string }> },
  headers: Record<string, string>,
  onEvent: (event: string, data: unknown) => void,
) {
  const res = await fetch(`${baseUrl}/api/v1/sessions/${sessionId}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body: JSON.stringify(payload),
  })

  if (!res.ok || !res.body) {
    throw new Error(`chat request failed: ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder("utf-8")
  let buffer = ""

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split("\n\n")
    buffer = frames.pop() || ""

    for (const frame of frames) {
      const lines = frame.split("\n")
      const eventLine = lines.find((line) => line.startsWith("event:"))
      const dataLine = lines.find((line) => line.startsWith("data:"))
      if (!eventLine || !dataLine) continue

      const event = eventLine.slice(6).trim()
      const raw = dataLine.slice(5).trim()

      try {
        onEvent(event, JSON.parse(raw))
      } catch {
        // 忽略损坏帧，保持流继续解析。
      }
    }
  }
}
```

## 7. 重连与 `seq` 策略
- 客户端在当前活跃流内维护 `last_seq`。
- 重连时发送新的 `client_seq` 轮次，并通过 `GET /sessions/{session_id}/messages` 恢复历史。
- 如果 `GET /sessions/{session_id}/messages` 返回 `404 SESSION_NOT_FOUND`，应将本地 `session` 视为过期并重新创建 `case/session`。
- UI 必须按 `seq` 将每一轮视为只追加数据。

## 8. 生产路径策略
- 咨询场景的生产路径仅走 middlend。
- 本地规则模块可以保留用于离线开发，但不能自动替代线上 SSE 结果。
- 任何流式失败都应按 `error` + `message_end` 处理，并向用户暴露重试交互。
