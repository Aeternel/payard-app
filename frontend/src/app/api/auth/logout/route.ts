import { NextResponse } from "next/server";

export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete("payyard_access");
  response.cookies.delete("payyard_refresh");
  return response;
}

