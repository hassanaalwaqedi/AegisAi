import { NextRequest, NextResponse } from "next/server";
import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

/**
 * Next.js does not load the monorepo's parent `.env`. For local development,
 * this server-only fallback reads it without ever exposing the credential to
 * browser code. Production must inject these variables into the server.
 */
function localRootEnvValue(name: string): string | undefined {
  if (process.env.NODE_ENV === "production") return undefined;

  try {
    const content = readFileSync(resolve(process.cwd(), "..", ".env"), "utf8");
    for (const line of content.split(/\r?\n/)) {
      const match = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
      if (!match || match[1] !== name) continue;

      const value = match[2];
      if (
        value.length >= 2 &&
        ((value.startsWith('"') && value.endsWith('"')) ||
          (value.startsWith("'") && value.endsWith("'")))
      ) {
        return value.slice(1, -1);
      }
      return value;
    }
  } catch {
    // A root .env is optional. The caller returns an explicit unavailable state.
  }

  return undefined;
}

function serverEnvValue(name: "AEGIS_API_URL" | "AEGIS_API_KEY") {
  return process.env[name] || localRootEnvValue(name);
}

function dashboardProxySignature(apiKey: string) {
  return createHmac("sha256", apiKey).update("aegis-dashboard-proxy-v1").digest("hex");
}

function getBackendUrl(path: string[], search: string) {
  const configuredUrl = serverEnvValue("AEGIS_API_URL") || "http://127.0.0.1:8080";
  const base = new URL(configuredUrl);
  const normalizedPath = path.map(encodeURIComponent).join("/");
  base.pathname = `${base.pathname.replace(/\/$/, "")}/${normalizedPath}`;
  base.search = search;
  return base;
}

async function proxy(request: NextRequest, context: RouteContext) {
  const apiKey = serverEnvValue("AEGIS_API_KEY");
  if (!apiKey) {
    return NextResponse.json(
      { detail: "Dashboard API proxy is not configured with a server-side API credential." },
      { status: 503 }
    );
  }

  const { path } = await context.params;
  const target = getBackendUrl(path, new URL(request.url).search);
  const headers = new Headers();
  headers.set("X-API-Key", apiKey);
  headers.set("X-Aegis-Internal-Proxy", dashboardProxySignature(apiKey));

  const accept = request.headers.get("accept");
  const contentType = request.headers.get("content-type");
  if (accept) headers.set("accept", accept);
  if (contentType) headers.set("content-type", contentType);

  try {
    const hasBody = !["GET", "HEAD"].includes(request.method);
    const response = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store"
    });

    const responseHeaders = new Headers();
    for (const name of ["content-type", "content-disposition", "cache-control"]) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }

    return new NextResponse(response.body, {
      status: response.status,
      headers: responseHeaders
    });
  } catch {
    return NextResponse.json(
      { detail: "The dashboard could not reach the backend service." },
      { status: 503 }
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
