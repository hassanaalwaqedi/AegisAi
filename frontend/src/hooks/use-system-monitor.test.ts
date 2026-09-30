import { describe, expect, it } from "vitest";

import type { IntelligenceContext } from "@/lib/intelligence-context";
import { nextSystemMonitorState, systemMonitorSnapshot } from "./use-system-monitor";

const observedAt = "2026-09-29T06:00:00.000Z";

function context(overrides: Record<string, unknown> = {}) {
  return {
    generatedAt: observedAt,
    overall: { status: "live", degradedReasons: [] },
    alerts: { items: [] },
    events: [],
    ...overrides,
  } as unknown as IntelligenceContext;
}

const liveFreshness = { status: "live" as const, observedAt };
const evidence = [{ kind: "event" as const, id: "evidence-1", label: "Verified", serverValidated: true }];

describe("system monitor", () => {
  it("starts in continuous watching mode for a healthy context", () => {
    const next = systemMonitorSnapshot(context(), false);
    expect(nextSystemMonitorState(null, next)).toMatchObject({ kind: "watching", count: 0 });
  });

  it("surfaces an already active verified high-risk record when the workspace opens", () => {
    const next = systemMonitorSnapshot(context({
      alerts: { items: [{ alertId: "alert-1", level: "HIGH", acknowledged: false, evidence, freshness: liveFreshness }] },
    }), false);
    expect(nextSystemMonitorState(null, next)).toMatchObject({ kind: "risk", count: 1 });
  });

  it("notifies the operator when a newly refreshed context contains a verified event", () => {
    const previous = systemMonitorSnapshot(context(), false);
    const next = systemMonitorSnapshot(context({
      events: [{ eventId: "event-1", riskLevel: "LOW", summary: "New verified activity", evidence, freshness: liveFreshness }],
    }), false);
    expect(nextSystemMonitorState(previous, next)).toMatchObject({ kind: "update", count: 1 });
  });

  it("prioritizes a system degradation over routine updates", () => {
    const previous = systemMonitorSnapshot(context(), false);
    const next = systemMonitorSnapshot(context({
      overall: { status: "degraded", degradedReasons: ["Redis unavailable"] },
      events: [{ eventId: "event-1", riskLevel: "HIGH", summary: "New verified activity", evidence, freshness: liveFreshness }],
    }), false);
    expect(nextSystemMonitorState(previous, next)).toMatchObject({ kind: "degraded" });
  });
});
