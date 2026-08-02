"use client";

import { resolveWebSocketUrl } from "@/lib/config";
import { AegisClientError } from "@/lib/errors";
import { websocketMessageSchema } from "@/lib/schemas";
import type { WebSocketConnectionState, WebSocketMessage } from "@/types";

type Listener = {
  onMessage: (message: WebSocketMessage) => void;
  onStateChange: (state: WebSocketConnectionState) => void;
  onError: (error: Error) => void;
};

export class AegisWebSocketClient {
  private socket?: WebSocket;
  private closedByConsumer = false;
  private reconnectAttempts = 0;
  private reconnectTimer?: number;
  private readonly url: string;
  private readonly listener: Listener;

  constructor(listener: Listener) {
    this.url = resolveWebSocketUrl();
    this.listener = listener;
  }

  connect() {
    if (!this.url) {
      this.listener.onStateChange("error");
      this.listener.onError(
        new AegisClientError("WebSocket URL is not configured.", "WEBSOCKET_DISCONNECTED")
      );
      return;
    }

    this.closedByConsumer = false;
    this.listener.onStateChange(this.reconnectAttempts > 0 ? "reconnecting" : "connecting");

    try {
      this.socket = new WebSocket(this.url);
    } catch (error) {
      this.listener.onStateChange("error");
      this.listener.onError(error instanceof Error ? error : new Error("WebSocket failed to initialize."));
      this.scheduleReconnect();
      return;
    }

    this.socket.onopen = () => {
      this.reconnectAttempts = 0;
      this.listener.onStateChange("connected");
    };

    this.socket.onmessage = (event) => {
      try {
        const json = JSON.parse(event.data);
        const parsed = websocketMessageSchema.safeParse(json);

        if (!parsed.success) {
          this.listener.onError(
            new AegisClientError(
              "Invalid WebSocket message schema.",
              "INVALID_RESPONSE_SCHEMA",
              undefined,
              parsed.error.flatten()
            )
          );
          return;
        }

        this.listener.onMessage(parsed.data);
      } catch (error) {
        this.listener.onError(error instanceof Error ? error : new Error("Unable to parse WebSocket message."));
      }
    };

    this.socket.onerror = () => {
      this.listener.onStateChange("error");
      this.listener.onError(
        new AegisClientError("WebSocket connection error.", "WEBSOCKET_DISCONNECTED")
      );
    };

    this.socket.onclose = () => {
      if (this.closedByConsumer) {
        this.listener.onStateChange("disconnected");
        return;
      }

      this.listener.onStateChange("reconnecting");
      this.scheduleReconnect();
    };
  }

  close() {
    this.closedByConsumer = true;
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
    this.socket?.close();
  }

  private scheduleReconnect() {
    if (this.closedByConsumer) return;

    const delay = Math.min(30000, 1000 * 2 ** this.reconnectAttempts);
    this.reconnectAttempts += 1;
    this.reconnectTimer = window.setTimeout(() => this.connect(), delay);
  }
}
