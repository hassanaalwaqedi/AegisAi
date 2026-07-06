"use client";

import { useEffect, useMemo, useState } from "react";
import { AegisWebSocketClient } from "@/lib/websocket-client";
import type { WebSocketConnectionState, WebSocketMessage } from "@/types";

export function useAegisWebSocket(enabled = true) {
  const [state, setState] = useState<WebSocketConnectionState>("idle");
  const [message, setMessage] = useState<WebSocketMessage | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const client = useMemo(
    () =>
      new AegisWebSocketClient({
        onMessage: setMessage,
        onStateChange: setState,
        onError: setError
      }),
    []
  );

  useEffect(() => {
    if (!enabled) return undefined;

    client.connect();
    return () => client.close();
  }, [client, enabled]);

  return {
    state,
    message,
    error
  };
}
