import { requestJson } from "../core/http";

export type SmsSendRequest = {
  phone: string;
};

export type SmsLoginRequest = {
  phone: string;
  code: string;
};

export type RefreshTokenRequest = {
  refresh_token: string;
};

export type TokenResponse = {
  access_token: string;
  refresh_token?: string | null;
  token_type: string;
};

export async function sendSmsCode(baseUrl: string, payload: SmsSendRequest) {
  return requestJson<{ success: boolean; phone: string; message: string }>(baseUrl, "/api/v1/auth/sms/send", {
    method: "POST",
    body: payload,
  });
}

export async function loginWithSms(baseUrl: string, payload: SmsLoginRequest) {
  return requestJson<TokenResponse>(baseUrl, "/api/v1/auth/sms/login", {
    method: "POST",
    body: payload,
  });
}

export async function refreshToken(baseUrl: string, payload: RefreshTokenRequest) {
  return requestJson<TokenResponse>(baseUrl, "/api/v1/auth/refresh", {
    method: "POST",
    body: payload,
  });
}

export async function logout(baseUrl: string) {
  return requestJson<{ success: boolean }>(baseUrl, "/api/v1/auth/logout", {
    method: "POST",
  });
}
