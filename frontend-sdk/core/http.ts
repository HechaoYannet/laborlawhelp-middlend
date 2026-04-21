export type AuthContext = {
  ownerToken?: string;
  accessToken?: string;
};

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH";
  auth?: AuthContext;
  body?: unknown;
};

export function buildAuthHeaders(auth?: AuthContext): Record<string, string> {
  if (!auth) {
    return {};
  }
  if (auth.accessToken) {
    return {
      Authorization: `Bearer ${auth.accessToken}`,
    };
  }
  if (auth.ownerToken) {
    return {
      "X-Anonymous-Token": auth.ownerToken,
    };
  }
  return {};
}

export async function requestJson<T>(
  baseUrl: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    ...buildAuthHeaders(options.auth),
  };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${baseUrl}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    throw new Error(`request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}
