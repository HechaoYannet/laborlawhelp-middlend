import { AuthContext, buildAuthHeaders } from "../core/http";
import { streamSse } from "../core/sse";

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
  auth: AuthContext,
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
  const response = await fetch(`${baseUrl}/api/v1/sessions/${sessionId}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildAuthHeaders(auth),
    },
    body: JSON.stringify(payload),
  });

  await streamSse(response, onEvent);
}
