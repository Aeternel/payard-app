import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const authenticated =
    request.cookies.has("payyard_access") || request.cookies.has("payyard_refresh");
  if (!authenticated && request.nextUrl.pathname.startsWith("/app")) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(login);
  }
  if (authenticated && request.nextUrl.pathname === "/login") {
    return NextResponse.redirect(new URL("/app", request.url));
  }
  return NextResponse.next();
}

export const config = { matcher: ["/app/:path*", "/login"] };
