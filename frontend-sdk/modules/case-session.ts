import { AuthContext, requestJson } from "../core/http";

export type CreateCaseRequest = {
  title: string;
  region_code: string;
};

export type CaseResponse = {
  id: string;
  owner_type: string;
  created_at: string;
  title: string;
  region_code: string;
  status: string;
};

export type SessionResponse = {
  id: string;
  case_id: string;
  status: string;
  openharness_session_id?: string | null;
};

export type MessageResponse = {
  id: string;
  role: string;
  content: string;
  created_at: string;
};

export type EndSessionResponse = {
  id: string;
  status: string;
  ended_at: string;
};

export async function createCase(baseUrl: string, payload: CreateCaseRequest, auth: AuthContext) {
  return requestJson<CaseResponse>(baseUrl, "/api/v1/cases", {
    method: "POST",
    auth,
    body: payload,
  });
}

export async function listCases(baseUrl: string, auth: AuthContext) {
  return requestJson<CaseResponse[]>(baseUrl, "/api/v1/cases", { auth });
}

export async function getCase(baseUrl: string, caseId: string, auth: AuthContext) {
  return requestJson<CaseResponse>(baseUrl, `/api/v1/cases/${caseId}`, { auth });
}

export async function createSession(baseUrl: string, caseId: string, auth: AuthContext) {
  return requestJson<SessionResponse>(baseUrl, `/api/v1/cases/${caseId}/sessions`, {
    method: "POST",
    auth,
  });
}

export async function listSessions(baseUrl: string, caseId: string, auth: AuthContext) {
  return requestJson<SessionResponse[]>(baseUrl, `/api/v1/cases/${caseId}/sessions`, { auth });
}

export async function listMessages(baseUrl: string, sessionId: string, auth: AuthContext) {
  return requestJson<MessageResponse[]>(baseUrl, `/api/v1/sessions/${sessionId}/messages`, { auth });
}

export async function endSession(baseUrl: string, sessionId: string, auth: AuthContext) {
  return requestJson<EndSessionResponse>(baseUrl, `/api/v1/sessions/${sessionId}/end`, {
    method: "PATCH",
    auth,
  });
}
