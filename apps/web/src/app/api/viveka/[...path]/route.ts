import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const MAX_BODY = 20 * 1024 * 1024 + 128 * 1024;
const routes = new Map([
  ["workbench", "POST"],
  ["workbench/sample", "GET"],
  ["labels", "GET"],
  ["model-card", "GET"],
]);
type Context = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, context: Context) {
  const path = (await context.params).path.join("/");
  if (!routes.has(path)) return NextResponse.json({ detail: "Unknown endpoint." }, { status: 404 });
  if (routes.get(path) !== request.method)
    return NextResponse.json(
      { detail: "Method not allowed." },
      { status: 405, headers: { Allow: routes.get(path)! } },
    );
  const headers = { "Cache-Control": "no-store" };
  try {
    const base = new URL(process.env.VIVEKA_API_URL || "http://127.0.0.1:8000");
    if (!["http:", "https:"].includes(base.protocol)) throw new Error("Invalid backend URL");
    const url = new URL(`${base.pathname.replace(/\/$/, "")}/v1/${path}`, base);
    const gstin = request.nextUrl.searchParams.get("company_gstin");
    if (gstin) url.searchParams.set("company_gstin", gstin);
    let body: Uint8Array | undefined;
    const contentType = request.headers.get("content-type");
    if (request.method === "POST") {
      if (!contentType?.startsWith("multipart/form-data;"))
        return NextResponse.json(
          { detail: "Send a ledger as a file upload." },
          { status: 415, headers },
        );
      if (Number(request.headers.get("content-length")) > MAX_BODY)
        return NextResponse.json({ detail: "The upload exceeds 20 MB." }, { status: 413, headers });
      // Count streamed bytes too: Content-Length may be missing or untrusted.
      const reader = request.body?.getReader();
      if (!reader)
        return NextResponse.json({ detail: "The upload is empty." }, { status: 400, headers });
      const chunks: Uint8Array[] = [];
      let size = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > MAX_BODY) {
          await reader.cancel();
          return NextResponse.json(
            { detail: "The upload exceeds 20 MB." },
            { status: 413, headers },
          );
        }
        chunks.push(value);
      }
      body = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {
        body.set(chunk, offset);
        offset += chunk.length;
      }
    }
    const configuredTimeout = Number(process.env.VIVEKA_API_TIMEOUT_MS || 300000);
    const timeout =
      Number.isFinite(configuredTimeout) && configuredTimeout > 0
        ? Math.min(configuredTimeout, 3600000)
        : 300000;
    const response = await fetch(url, {
      method: request.method,
      headers: contentType ? { "Content-Type": contentType } : {},
      body: body as BodyInit | undefined,
      cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(timeout)]),
    });
    if (response.status >= 500)
      return NextResponse.json(
        {
          detail:
            "The classification service could not process this request. Check the file or try again.",
        },
        { status: 502, headers },
      );
    if (!response.headers.get("content-type")?.includes("application/json"))
      return NextResponse.json(
        { detail: "The backend returned an unexpected response. Check the service address." },
        { status: 502, headers },
      );
    return new NextResponse(response.body, {
      status: response.status,
      headers: { ...headers, "Content-Type": "application/json" },
    });
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "TimeoutError";
    return NextResponse.json(
      {
        detail: timedOut
          ? "Classification took too long. Try a smaller ledger or increase the service timeout."
          : "The classification service is unavailable. Start the Viveka backend and try again.",
      },
      { status: timedOut ? 504 : 503, headers },
    );
  }
}
export const GET = forward;
export const POST = forward;
