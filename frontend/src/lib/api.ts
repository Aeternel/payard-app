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

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/backend/${path.replace(/^\//, "")}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
    },
    credentials: "same-origin",
  });
  const payload = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    const detail = payload?.error?.detail ?? payload?.detail ?? payload;
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

