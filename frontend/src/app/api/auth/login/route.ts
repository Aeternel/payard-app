import { NextRequest, NextResponse } from "next/server";

const backend = process.env.INTERNAL_API_URL ?? "http://localhost:8001/api/v1";

export async function POST(request: NextRequest) {
  try {
    const response = await fetch(`${backend}/auth/login/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    const body = await response.text();
    let data: Record<string, unknown>;

    try {
      data = body ? JSON.parse(body) : {};
    } catch {
      return NextResponse.json(
        { error: { detail: "Authentication service returned an invalid response." } },
        { status: 502 },
      );
    }

    if (!response.ok) {
      return NextResponse.json(
        Object.keys(data).length
          ? data
          : { error: { detail: "Authentication service rejected the request." } },
        { status: response.status },
      );
    }
    if (
      typeof data.access !== "string"
      || typeof data.refresh !== "string"
      || !data.user
      || !data.company
    ) {
      return NextResponse.json(
        { error: { detail: "Authentication service returned an incomplete response." } },
        { status: 502 },
      );
    }

    const result = NextResponse.json({
      user: data.user,
      company: data.company,
      role: data.role,
    });
    const secure = process.env.NODE_ENV === "production";
    result.cookies.set("payyard_access", data.access, {
      httpOnly: true, secure, sameSite: "lax", maxAge: 15 * 60, path: "/",
    });
    result.cookies.set("payyard_refresh", data.refresh, {
      httpOnly: true, secure, sameSite: "strict", maxAge: 7 * 24 * 60 * 60, path: "/",
    });
    return result;
  } catch {
    return NextResponse.json(
      { error: { detail: "Authentication service is temporarily unavailable." } },
      { status: 503 },
    );
  }
}
