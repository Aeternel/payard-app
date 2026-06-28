"use client";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public details?: unknown,
  ) {
    super(message);
  }
}

export function apiUrl(path: string) {
  return `/api/backend/${path.replace(/^\//, "")}`;
}

async function readPayload(response: Response) {
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
    },
    credentials: "same-origin",
  });
  const payload = await readPayload(response);
  if (!response.ok) {
    const detail = payload && typeof payload === "object"
      ? (payload as { error?: { detail?: unknown }; detail?: unknown }).error?.detail
        ?? (payload as { detail?: unknown }).detail
        ?? payload
      : payload;
    throw new ApiError(
      typeof detail === "string" ? detail : "Request failed",
      response.status,
      detail,
    );
  }
  return payload as T;
}

export async function fetchAll<T>(path: string): Promise<T[]> {
  const data = await apiFetch<{ results?: T[] } | T[]>(path);
  return Array.isArray(data) ? data : data.results ?? [];
}
