import { streamChat as streamChatWithAuth, type ChatAttachment, type ChatPayload } from "./modules/chat";

export type { ChatAttachment, ChatPayload };

export async function streamChat(
  baseUrl: string,
  sessionId: string,
  payload: ChatPayload,
  ownerToken: string,
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
  return streamChatWithAuth(baseUrl, sessionId, payload, { ownerToken }, onEvent);
}
