"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { RadioTower } from "lucide-react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/layout/states";
import { createAuthenticatedWebSocket, resolveCameraWebSocketUrl } from "@/lib/config";
import { cameraWebSocketMessageSchema } from "@/lib/schemas";
import { formatOperatorLabel, formatOperatorList } from "@/lib/data-format";
import { formatTime } from "@/lib/utils";
import { useCameraEventsQuery } from "@/hooks/use-aegis-api";
import type { Camera, RiskEvent } from "@/types";

function eventKey(event: RiskEvent) {
  return String(event.event_id ?? event.id ?? `${event.timestamp}-${event.risk_level}-${event.status ?? ""}`);
}

function severityVariant(level?: string) {
  const normalized = level?.toUpperCase();
  if (normalized === "CRITICAL") return "critical";
  if (normalized === "HIGH") return "danger";
  if (normalized === "MEDIUM" || normalized === "CANDIDATE_MEDIUM") return "warning";
  if (normalized === "LOW") return "success";
  return "outline";
}

export function CameraEvents({ camera }: { camera?: Camera }) {
  const query = useCameraEventsQuery(camera?.camera_id);
  const [socketEvents, setSocketEvents] = useState<RiskEvent[]>([]);
  const [socketMessage, setSocketMessage] = useState("");
  const closedRef = useRef(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    const resetTimer = window.setTimeout(() => {
      setSocketEvents([]);
      setSocketMessage("");
    }, 0);
    if (!camera) return () => window.clearTimeout(resetTimer);

    const url = resolveCameraWebSocketUrl(camera.camera_id, "events");
    if (!url) {
      const unavailableTimer = window.setTimeout(
        () => setSocketMessage("Live event updates are not configured."),
        0
      );
      return () => {
        window.clearTimeout(resetTimer);
        window.clearTimeout(unavailableTimer);
      };
    }

    let socket: WebSocket | undefined;
    let retries = 0;
    closedRef.current = false;

    async function connect() {
      if (closedRef.current) return;
      try {
        socket = await createAuthenticatedWebSocket(url);
        if (closedRef.current) {
          socket.close();
          return;
        }
      } catch {
        setSocketMessage("Live event updates are temporarily unavailable.");
        return;
      }

      socket.onopen = () => {
        retries = 0;
        setSocketMessage("");
      };

      socket.onmessage = (event) => {
        try {
          const parsed = cameraWebSocketMessageSchema.safeParse(JSON.parse(event.data));
          if (!parsed.success) {
            setSocketMessage("A live event update could not be read.");
            return;
          }
          if (parsed.data.events?.length) {
            setSocketEvents((current) => [...current, ...(parsed.data.events ?? [])].slice(-50));
          }
          if (parsed.data.message) setSocketMessage("Live event updates need attention.");
        } catch {
          setSocketMessage("A live event update could not be read.");
        }
      };

      socket.onerror = () => {
        setSocketMessage("Live event updates are temporarily unavailable.");
      };

      socket.onclose = () => {
        if (closedRef.current) return;
        retries += 1;
        timerRef.current = window.setTimeout(() => void connect(), Math.min(15000, 1000 * 2 ** retries));
      };
    }

    void connect();

    return () => {
      closedRef.current = true;
      window.clearTimeout(resetTimer);
      if (timerRef.current) window.clearTimeout(timerRef.current);
      socket?.close();
    };
  }, [camera]);

  const events = useMemo(() => {
    const merged = [...(query.data?.events ?? []), ...socketEvents];
    const map = new Map<string, RiskEvent>();
    merged.forEach((event) => map.set(eventKey(event), event));
    return Array.from(map.values()).slice(-30).reverse();
  }, [query.data?.events, socketEvents]);

  if (!camera) {
    return <EmptyState title="Select a camera" description="Camera-specific risk events appear after selecting a registered source." />;
  }

  if (query.isLoading) return <LoadingState label="Loading camera events" />;
  if (query.isError) return <ErrorState error={query.error} title="Camera activity unavailable" />;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Camera Events</CardTitle>
          <CardDescription>{camera.camera_id}</CardDescription>
        </div>
        <RadioTower className="h-5 w-5 text-signal-cyan" aria-hidden />
      </CardHeader>

      {socketMessage ? <p className="mb-3 rounded-md border border-amber-300/20 bg-amber-300/[0.06] p-3 text-sm text-amber-100">{socketMessage}</p> : null}

      {events.length === 0 ? (
        <EmptyState title="No alerts for this camera" description="New security activity will appear here when it needs review." />
      ) : (
        <div className="space-y-3">
          {events.map((event) => {
            const level = event.risk_level ?? event.severity ?? event.level;
            const extra = event as Record<string, unknown>;
            const fallbackType = typeof extra.event_type === "string" ? extra.event_type : "Camera event";
            const headline = [event.title, event.reason, event.description, fallbackType].find(
              (value): value is string => typeof value === "string" && value.length > 0
            );
            return (
              <article key={eventKey(event)} className="rounded-lg border border-white/10 bg-white/[0.035] p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Badge variant={severityVariant(level)}>{String(level ?? fallbackType)}</Badge>
                  <span className="text-xs text-slate-500">{formatTime(String(event.timestamp ?? ""))}</span>
                </div>
                <p className="mt-2 text-sm font-medium text-white">{headline}</p>
                {event.risk_score !== undefined ? <p className="mt-1 text-xs text-slate-400">Risk score {event.risk_score.toFixed(3)}</p> : null}
                {event.track_id ? <p className="mt-1 text-xs text-slate-500">Track {String(event.track_id)}</p> : null}
                <div className="mt-2 grid gap-1 text-xs text-slate-500 sm:grid-cols-2">
                  <span>Verification: {formatOperatorLabel(event.verification_status)}</span>
                  <span>Evidence: {formatOperatorLabel(event.evidence_type)}</span>
                  <span>Activity source: {formatOperatorList(event.model_source)}</span>
                  <span>Why it needs review: {formatOperatorList(event.reason_codes)}</span>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </Card>
  );
}
