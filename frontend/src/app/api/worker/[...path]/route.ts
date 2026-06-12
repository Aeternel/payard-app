import { NextRequest, NextResponse } from "next/server";

const backend = process.env.INTERNAL_API_URL ?? "http://localhost:8001/api/v1";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const token = request.headers.get("x-worker-token");
  if (!token) return NextResponse.json({ detail: "Worker token required." }, { status: 401 });
  const response = await fetch(`${backend}/worker/${path.join("/")}/${request.nextUrl.search}`, {
    method: request.method,
    headers: {
      Authorization: `Worker ${token}`,
      ...(request.headers.get("content-type")
        ? { "Content-Type": request.headers.get("content-type")! }
        : {}),
    },
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    // @ts-expect-error Node fetch requires duplex for streamed request bodies.
    duplex: "half",
    cache: "no-store",
  });
  return new NextResponse(response.body, {
    status: response.status,
    headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" },
  });
}

export const GET = proxy;
export const POST = proxy;
