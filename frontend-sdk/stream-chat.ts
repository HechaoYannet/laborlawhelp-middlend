export type ChatAttachment = {
  id: string;
  name: string;
  url: string;
  mime_type: string;
};

export type ChatPayload = {
  message: string;
  client_seq: number;
  attachments?: ChatAttachment[];
  locale?: string;
  policy_version?: string;
  client_capabilities?: string[];
};

export async function streamChat(
  baseUrl: string,
  sessionId: string,
  payload: ChatPayload,
  ownerToken: string,
  onEvent: (event: string, data: any) => void,
): Promise<void> {
  const response = await fetch(`${baseUrl}/api/v1/sessions/${sessionId}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Anonymous-Token": ownerToken,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    throw new Error(`stream chat failed with status ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";

    for (const frame of frames) {
      const lines = frame.split("\n");
      const eventLine = lines.find((line) => line.startsWith("event:"));
      const dataLine = lines.find((line) => line.startsWith("data:"));
      if (!eventLine || !dataLine) {
        continue;
      }

      const event = eventLine.slice(6).trim();
      const data = JSON.parse(dataLine.slice(5).trim());
      onEvent(event, data);
    }
  }
}
