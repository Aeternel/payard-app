import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const backend = process.env.INTERNAL_API_URL ?? "http://localhost:8001/api/v1";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const cookieStore = await cookies();
  let access = cookieStore.get("payyard_access")?.value;
  const target = `${backend}/${path.join("/")}/${request.nextUrl.search}`;
  const body = ["GET", "HEAD"].includes(request.method)
    ? undefined
    : await request.arrayBuffer();
  const makeRequest = (token?: string) =>
    fetch(target, {
      method: request.method,
      headers: {
        ...(request.headers.get("content-type")
          ? { "Content-Type": request.headers.get("content-type")! }
          : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        "X-Device-ID": request.headers.get("x-device-id") ?? "payyard-web",
      },
      body,
      cache: "no-store",
    });

  let response = await makeRequest(access);
  let newAccess: string | undefined;
  let newRefresh: string | undefined;
  if (response.status === 401) {
    const refresh = cookieStore.get("payyard_refresh")?.value;
    if (refresh) {
      const refreshed = await fetch(`${backend}/auth/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh }),
        cache: "no-store",
      });
      if (refreshed.ok) {
        const tokens = await refreshed.json();
        newAccess = tokens.access;
        newRefresh = tokens.refresh;
        access = newAccess;
        response = await makeRequest(access);
      }
    }
  }
  const responseHeaders: Record<string, string> = {
    "Content-Type": response.headers.get("content-type") ?? "application/json",
  };
  const contentDisposition = response.headers.get("content-disposition");
  if (contentDisposition) responseHeaders["Content-Disposition"] = contentDisposition;
  const contentLength = response.headers.get("content-length");
  if (contentLength) responseHeaders["Content-Length"] = contentLength;
  const result = new NextResponse(response.body, {
    status: response.status,
    headers: responseHeaders,
  });
  if (newAccess) {
    result.cookies.set("payyard_access", newAccess, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 15 * 60,
      path: "/",
    });
  }
  if (newRefresh) {
    result.cookies.set("payyard_refresh", newRefresh, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "strict",
      maxAge: 7 * 24 * 60 * 60,
      path: "/",
    });
  }
  return result;
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
