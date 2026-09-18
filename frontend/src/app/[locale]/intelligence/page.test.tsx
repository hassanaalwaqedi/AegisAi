import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IntelligenceCommandCenter } from "@/components/intelligence/intelligence-command-center";
import type { IntelligenceContextState } from "@/hooks/useIntelligenceContext";
import { intelligenceContextSchema } from "@/lib/intelligence-context";
import { executeOperatorCommand } from "@/lib/operator-api";
import messages from "../../../../messages/en.json";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/hooks/use-aegis-api", () => ({
  useEvidenceSearchStatusQuery: () => ({ data: { state: "ready", indexed_evidence: 42, pending_evidence: 0 } }),
}));
vi.mock("@/lib/operator-api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/operator-api")>();
  return { ...original, executeOperatorCommand: vi.fn() };
});

const timestamp = "2026-09-18T12:00:00.000Z";

function state(): IntelligenceContextState {
  return {
    phase: "ready",
    error: null,
    isStale: false,
    refreshedAt: new Date(timestamp),
    refresh: vi.fn(),
    context: intelligenceContextSchema.parse({
      schemaVersion: "1.0", contextId: "ctx-1", generatedAt: timestamp, refreshAfterSeconds: 10,
      overall: { status: "live", degradedReasons: [], checks: [{ name: "api", status: "live", observedAt: timestamp }] },
      cameras: { total: 2, totalConfigured: 2, online: 1, offline: 1, stale: 0, unavailable: 0, items: [{ cameraId: "camera-1", name: "North Gate", runtime: "live", lastFrameAt: timestamp, freshness: { observedAt: timestamp, status: "live" } }], freshness: { observedAt: timestamp, status: "live" } },
      alerts: { activeCount: 1, items: [{ alertId: "alert-1", level: "HIGH", acknowledged: false, evidence: [{ kind: "alert", id: "alert-1", label: "High risk", serverValidated: true }], freshness: { observedAt: timestamp, status: "live" } }], freshness: { observedAt: timestamp, status: "live" } },
      incidents: { capability: "live", activeCount: 1 },
      events: [{ eventId: "event-1", riskLevel: "HIGH", riskScore: .8, summary: "Restricted-zone activity", evidence: [{ kind: "event", id: "event-1", label: "Restricted-zone activity", serverValidated: true }], freshness: { observedAt: timestamp, status: "live" } }],
      tracks: [{ trackId: "track-1", cameraId: "camera-1", className: "person", riskScore: .4, evidence: [{ kind: "track", id: "track-1", label: "person", serverValidated: true }], freshness: { observedAt: timestamp, status: "live" } }],
      detections: { recentCount: 3, freshness: { observedAt: timestamp, status: "live" } },
      semantic: { capability: "live", mode: "live_evidence", evidence: [], freshness: { observedAt: timestamp, status: "live" } },
      pipeline: { running: true, stages: [{ name: "tracking", status: "live", observedAt: timestamp }], freshness: { observedAt: timestamp, status: "live" } },
      ai: { chat: "live", providerConfigured: true, evidenceGrounding: "live", voice: { pushToTalk: "unavailable", handsFree: "unavailable", reason: "Not configured" } },
      suggestions: [],
    }),
  };
}

function renderCenter() {
  return render(<NextIntlClientProvider locale="en" messages={messages}><IntelligenceCommandCenter state={state()} /></NextIntlClientProvider>);
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("Aegis Intelligence operator", () => {
  it("renders only values supplied by the intelligence contracts", () => {
    renderCenter();
    expect(screen.getByRole("heading", { name: "Aegis AI Operator" })).toBeInTheDocument();
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("Restricted-zone activity")).toBeInTheDocument();
  });

  it("executes a suggestion through the authenticated operator API and renders its real trace", async () => {
    vi.mocked(executeOperatorCommand).mockResolvedValue({
      action: "RISK_QUERY", intent: "Risk", answer: "Found 1 verified event record.", panel: "events", target: "/events?risk=high",
      result: { events: [{ event_id: "event-1", message: "Restricted-zone activity", camera_id: "camera-1", risk_level: "HIGH", timestamp }] },
      sources: [{ type: "event", id: "event-1", label: "Restricted-zone activity" }],
      trace: [{ key: "understood", label: "Request understood", status: "completed" }], response_language: "English", error: null,
    });
    renderCenter();
    fireEvent.click(screen.getByRole("button", { name: "Show high-risk events from the last hour" }));
    await waitFor(() => expect(executeOperatorCommand).toHaveBeenCalled());
    expect(await screen.findByText("Found 1 verified event record.")).toBeInTheDocument();
    expect(screen.getByText("Request understood")).toBeInTheDocument();
    expect(document.querySelector(".cinematic-intelligence")).toHaveAttribute("data-presence", "executing");
    expect(document.querySelector(".cinematic-result-projection")).toBeInTheDocument();
  });
});
