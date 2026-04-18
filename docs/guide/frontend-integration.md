# Frontend Integration Guide (Next.js)

## 1. Lifecycle (Must Follow)
1. `POST /cases`
2. `POST /cases/{case_id}/sessions`
3. `POST /sessions/{session_id}/chat` with stream parsing

Chat is forbidden before session creation.

## 2. Client State Model
| State | Required Fields |
|---|---|
| owner | `owner_type`, `anonymous_token` or JWT |
| case | `case_id`, `title`, `region_code` |
| session | `session_id`, `status`, `last_active_at` |
| stream | `current_message_id`, `last_seq`, `is_streaming` |

## 3. Stream Parser Requirements
- Use `fetch` + `ReadableStream`.
- Parse SSE by frame separator `\n\n`.
- Handle UTF-8 split chunks safely with `TextDecoder` streaming mode.
- Dispatch by `event` type.
- Keep monotonic `seq`; drop duplicated or older deltas.

## 4. Recommended Event Handling
| Event | UI Action |
|---|---|
| `message_start` | Create pending assistant bubble |
| `content_delta` | Append token text by seq |
| `tool_call` | Show status badge "处理中" |
| `tool_result` | Update status badge with summary |
| `final` | Fill summary/reference sidebar |
| `message_end` | Mark assistant message complete |
| `error` | End stream, show retry button |

## 5. TypeScript Example

```ts
export async function streamChat(
  baseUrl: string,
  sessionId: string,
  payload: { message: string; client_seq: number; attachments?: Array<{id: string; name: string; url: string; mime_type: string}> },
  headers: Record<string, string>,
  onEvent: (event: string, data: any) => void,
) {
  const res = await fetch(`${baseUrl}/api/v1/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok || !res.body) {
    throw new Error(`chat request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";

    for (const frame of frames) {
      const eventLine = frame.split("\n").find((l) => l.startsWith("event:"));
      const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!eventLine || !dataLine) continue;

      const event = eventLine.slice(6).trim();
      const data = JSON.parse(dataLine.slice(5).trim());
      onEvent(event, data);
    }
  }
}
```

## 6. Reconnect and Seq Policy
- Client keeps `last_seq` in memory.
- On reconnect, send same `client_seq` and include `last_seq` in custom header if implemented.
- UI must treat stream as append-only by `seq`.

## 7. Fallback Policy
- Default no local rule fallback.
- Only enable fallback when backend explicitly returns fallback signal.
- Fallback must show visual marker: "本次结果来自回退逻辑".
