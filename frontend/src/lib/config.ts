const DASHBOARD_API_PROXY = "/api/backend";

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, "");
}

export const appConfig = {
  // Requests flow through the Next.js server proxy. This keeps AEGIS_API_KEY
  // server-side instead of embedding it in the browser bundle.
  apiUrl: DASHBOARD_API_PROXY,
  wsUrl: process.env.NEXT_PUBLIC_WS_URL || process.env.NEXT_PUBLIC_AEGIS_WS_URL
    ? trimTrailingSlash(process.env.NEXT_PUBLIC_WS_URL || process.env.NEXT_PUBLIC_AEGIS_WS_URL || "")
    : "",
  requestTimeoutMs: 10000
};

type WebSocketTokenResponse = {
  token?: unknown;
  protocol?: unknown;
};

/**
 * Obtain an ephemeral backend-issued WebSocket credential. The browser never
 * receives the long-lived AEGIS_API_KEY; the Next server proxy performs that
 * authenticated exchange.
 */
export async function createAuthenticatedWebSocket(url: string): Promise<WebSocket> {
  const response = await fetch(`${appConfig.apiUrl}/ws/token`, {
    method: "POST",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error("WebSocket authentication is unavailable.");
  }

  const payload = (await response.json()) as WebSocketTokenResponse;
  if (typeof payload.token !== "string" || typeof payload.protocol !== "string") {
    throw new Error("WebSocket authentication response is invalid.");
  }

  return new WebSocket(url, [payload.protocol, payload.token]);
}

export function resolveWebSocketUrl() {
  if (appConfig.wsUrl) return appConfig.wsUrl;

  try {
    const url = new URL(appConfig.apiUrl);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = "/ws";
    url.search = "";
    return url.toString();
  } catch {
    return "";
  }
}

export function resolveCameraWebSocketUrl(cameraId: string, channel: "frames" | "events") {
  const base = (() => {
    if (appConfig.wsUrl) {
      try {
        const configured = new URL(appConfig.wsUrl);
        configured.pathname = "";
        configured.search = "";
        return configured;
      } catch {
        return null;
      }
    }

    try {
      const url = new URL(appConfig.apiUrl);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      url.pathname = "";
      url.search = "";
      return url;
    } catch {
      return null;
    }
  })();

  if (!base) return "";
  base.pathname = `/ws/cameras/${encodeURIComponent(cameraId)}/${channel}`;
  return base.toString();
}
