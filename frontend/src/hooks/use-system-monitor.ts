"use client";

import { useEffect, useRef, useState } from "react";

import type { IntelligenceContext } from "@/lib/intelligence-context";

export type SystemMonitorKind = "connecting" | "watching" | "update" | "risk" | "degraded" | "recovered";

export type SystemMonitorState = {
  kind: SystemMonitorKind;
  count: number;
  observedAt: string | null;
};

export type SystemMonitorSnapshot = {
  degradedKey: string;
  highRiskIds: Set<string>;
  verifiedEventIds: Set<string>;
  observedAt: string;
};

function isFreshVerified(record: { freshness: { status: string }; evidence: Array<{ serverValidated?: boolean }> }) {
  return record.freshness.status === "live" && record.evidence.some((evidence) => evidence.serverValidated === true);
}

function highRisk(level: string | null | undefined) {
  const normalized = level?.trim().toUpperCase();
  return normalized === "HIGH" || normalized === "CRITICAL";
}

export function systemMonitorSnapshot(context: IntelligenceContext, isStale: boolean): SystemMonitorSnapshot {
  const highRiskIds = new Set<string>();
  const verifiedEventIds = new Set<string>();

  for (const alert of context.alerts.items) {
    if (!alert.acknowledged && highRisk(alert.level) && isFreshVerified(alert)) highRiskIds.add(`alert:${alert.alertId}`);
  }
  for (const event of context.events) {
    if (!isFreshVerified(event)) continue;
    verifiedEventIds.add(event.eventId);
    if (highRisk(event.riskLevel)) highRiskIds.add(`event:${event.eventId}`);
  }

  const status = isStale ? "stale" : context.overall.status;
  const degradedKey = [status, ...context.overall.degradedReasons.slice().sort()].join("|");
  return { degradedKey, highRiskIds, verifiedEventIds, observedAt: context.generatedAt };
}

function differenceCount(next: Set<string>, previous: Set<string>) {
  let count = 0;
  next.forEach((item) => { if (!previous.has(item)) count += 1; });
  return count;
}

function isDegraded(snapshot: SystemMonitorSnapshot) {
  return snapshot.degradedKey !== "live";
}

/**
 * Produces one operator-facing change at a time. It ignores the first normal
 * context as a baseline, while still surfacing an already active risk or a
 * degraded service immediately when the workspace opens.
 */
export function nextSystemMonitorState(previous: SystemMonitorSnapshot | null, next: SystemMonitorSnapshot): SystemMonitorState {
  if (!previous) {
    if (isDegraded(next)) return { kind: "degraded", count: 1, observedAt: next.observedAt };
    if (next.highRiskIds.size) return { kind: "risk", count: next.highRiskIds.size, observedAt: next.observedAt };
    return { kind: "watching", count: 0, observedAt: next.observedAt };
  }

  if (previous.degradedKey !== next.degradedKey) {
    return isDegraded(next)
      ? { kind: "degraded", count: 1, observedAt: next.observedAt }
      : { kind: "recovered", count: 0, observedAt: next.observedAt };
  }

  const newHighRisk = differenceCount(next.highRiskIds, previous.highRiskIds);
  if (newHighRisk) return { kind: "risk", count: newHighRisk, observedAt: next.observedAt };

  const newVerifiedEvents = differenceCount(next.verifiedEventIds, previous.verifiedEventIds);
  if (newVerifiedEvents) return { kind: "update", count: newVerifiedEvents, observedAt: next.observedAt };

  return { kind: "watching", count: 0, observedAt: next.observedAt };
}

/** Continuously observes the context refreshes already owned by the page. */
export function useSystemMonitor({
  context,
  phase,
  isStale,
}: {
  context: IntelligenceContext | null;
  phase: "loading" | "ready" | "error";
  isStale: boolean;
}) {
  const previousRef = useRef<SystemMonitorSnapshot | null>(null);
  const [state, setState] = useState<SystemMonitorState>({ kind: "connecting", count: 0, observedAt: null });

  useEffect(() => {
    const task = window.setTimeout(() => {
      if (!context) {
        if (phase === "error") setState({ kind: "degraded", count: 1, observedAt: null });
        return;
      }
      const next = systemMonitorSnapshot(context, isStale);
      setState(nextSystemMonitorState(previousRef.current, next));
      previousRef.current = next;
    }, 0);
    return () => window.clearTimeout(task);
  }, [context, isStale, phase]);

  return state;
}
