# Frontend Integration Guide (Next.js)

## 1. Lifecycle (Must Follow)
1. `POST /cases`
2. `POST /cases/{case_id}/sessions`
3. `POST /sessions/{session_id}/chat/stream` and parse stream

Chat is forbidden before session creation.

## 2. Client State Model
| State | Required Fields |
|---|---|
| owner | `owner_type`, `anonymous_token` or JWT |
| case | `case_id`, `title`, `region_code` |
| session | `session_id`, `status`, `last_active_at` |
| stream | `current_message_id`, `trace_id`, `last_seq`, `is_streaming` |

## 3. Stream Parser Requirements
- Use `fetch` + `ReadableStream` (POST).
- Parse SSE by frame separator `\n\n`.
- Handle UTF-8 split chunks safely with `TextDecoder` streaming mode.
- Dispatch by `event` type.
- Keep monotonic `seq`; drop duplicated or older deltas.
- Ignore unknown events and unknown fields for forward compatibility.
- Treat `message_end` as the only stream completion signal for one assistant turn.

## 4. Event Contract and UI Handling
| Event | Required Fields | UI Action |
|---|---|---|
| `message_start` | `message_id`, `trace_id` | Create pending assistant bubble |
| `content_delta` | `delta`, `seq`, `trace_id` | Append token text by seq |
| `tool_call` | `tool_name`, `trace_id` | Show status badge "处理中" |
| `tool_result` | `tool_name`, `result_summary`, `references`, `trace_id` | Update status and render cards when `card_type/card_payload` exists |
| `final` | `message_id`, `summary`, `references`, `rule_version`, `finish_reason`, `trace_id` | Fill summary/reference/sidebar data |
| `error` | `code`, `message`, `retryable`, `trace_id` | Mark retryable error without dropping received content |
| `message_end` | `message_id`, `trace_id` | Mark assistant message complete |

`tool_result` optional extension fields:
- `card_type`
- `card_title`
- `card_payload`
- `card_actions`

## 5. TypeScript Example

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
        // Skip malformed frame and keep stream alive.
      }
    }
  }
}
```

## 6. Reconnect and Seq Policy
- Client keeps `last_seq` in memory for the active stream.
- On reconnect, send a new `client_seq` turn and recover history via `GET /sessions/{session_id}/messages`.
- UI must treat each turn as append-only by `seq`.

## 7. Production Path Policy
- Consultation production path is middleware-only.
- Local rule modules can be kept for offline development, but must not auto-replace online SSE results.
- Any stream failure should follow `error` + `message_end` handling and expose retry UX.
