import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  activityFromContext,
  buildCapabilityNodes,
  IntelligencePageContent,
} from "./page";
import {
  intelligenceContextSchema,
  type IntelligenceContext,
} from "@/lib/intelligence-context";
import type { IntelligenceContextState } from "@/hooks/useIntelligenceContext";

vi.mock("@/components/intelligence/AegisVoiceCore", () => ({
  default: ({ contextAvailability, onOpenOperations }: { contextAvailability: string; onOpenOperations?: () => void }) => (
    <div data-testid="aegis-voice-core">
      Voice Core: {contextAvailability}
      <button type="button" onClick={onOpenOperations}>Settings</button>
    </div>
  ),
}));

vi.mock("@/components/intelligence/ActivityFeed", () => ({
  default: ({ items, emptyMessage }: { items: unknown[]; emptyMessage: string }) => (
    <div data-testid="activity-feed">
      {items.length ? `Returned evidence: ${items.length}` : emptyMessage}
    </div>
  ),
}));

const TIMESTAMP = "2026-07-30T12:00:00.000Z";

afterEach(cleanup);

function makeContext(): IntelligenceContext {
  return intelligenceContextSchema.parse({
    schemaVersion: "1.0",
    contextId: "test-context",
    generatedAt: TIMESTAMP,
    refreshAfterSeconds: 10,
    overall: {
      status: "live",
      degradedReasons: [],
      checks: [
        { name: "api", status: "live", observedAt: TIMESTAMP },
        { name: "database", status: "live", observedAt: TIMESTAMP },
        { name: "redis", status: "live", observedAt: TIMESTAMP },
        { name: "event_stream", status: "live", observedAt: TIMESTAMP },
        { name: "pipeline", status: "live", observedAt: TIMESTAMP },
        { name: "model", status: "live", observedAt: TIMESTAMP },
        { name: "persistence", status: "live", observedAt: TIMESTAMP },
      ],
    },
    cameras: {
      total: 1,
      totalConfigured: 1,
      online: 1,
      offline: 0,
      stale: 0,
      unavailable: 0,
      items: [
        {
          cameraId: "camera-1",
          name: "Camera 1",
          runtime: "live",
          lastFrameAt: TIMESTAMP,
          freshness: { observedAt: TIMESTAMP, status: "live" },
        },
      ],
      freshness: { observedAt: TIMESTAMP, status: "live" },
    },
    alerts: {
      activeCount: 0,
      items: [],
      freshness: { observedAt: TIMESTAMP, status: "live" },
    },
    incidents: {
      capability: "unavailable",
      reason: "Incident management is not implemented.",
      activeCount: null,
    },
    events: [],
    tracks: [],
    detections: {
      recentCount: 0,
      freshness: { observedAt: TIMESTAMP, status: "live" },
    },
    semantic: {
      capability: "live",
      mode: "live_evidence",
      evidence: [],
      freshness: { observedAt: TIMESTAMP, status: "live" },
    },
    pipeline: {
      running: true,
      stages: [
        { name: "tracking", status: "live", observedAt: TIMESTAMP },
        { name: "risk", status: "live", observedAt: TIMESTAMP },
      ],
      freshness: { observedAt: TIMESTAMP, status: "live" },
    },
    ai: {
      chat: "degraded",
      providerConfigured: false,
      evidenceGrounding: "unavailable",
      reason: "No AI provider is configured.",
      voice: {
        pushToTalk: "degraded",
        handsFree: "unavailable",
        reason: "Hands-free voice is not implemented.",
      },
    },
    suggestions: [],
  });
}

function makeState(
  overrides: Partial<IntelligenceContextState> = {},
): IntelligenceContextState {
  return {
    phase: "ready",
    context: makeContext(),
    error: null,
    isStale: false,
    refreshedAt: new Date(TIMESTAMP),
    refresh: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

describe("IntelligencePageContent Phase 0 truth states", () => {
  it("renders loading without fabricated operational values", () => {
    render(
      <IntelligencePageContent
        state={makeState({ phase: "loading", context: null, refreshedAt: null })}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(/Context loading/i);
    expect(screen.getByTestId("aegis-voice-core")).toHaveTextContent("Voice Core: unavailable");
    expect(screen.queryByTestId("activity-feed")).not.toBeInTheDocument();
    expect(screen.queryByText(/All Systems Normal/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/AI Confidence/i)).not.toBeInTheDocument();
  });

  it("renders an explicit unavailable/offline state when context retrieval fails", () => {
    render(
      <IntelligencePageContent
        state={makeState({
          phase: "error",
          context: null,
          error: new Error("The dashboard could not reach the intelligence backend."),
          refreshedAt: null,
        })}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(/Context unavailable/i);
    expect(screen.getByRole("alert")).toHaveTextContent(/dashboard could not reach the intelligence backend/i);
  });

  it("renders a stale notice instead of treating an expired context as live", () => {
    render(<IntelligencePageContent state={makeState({ isStale: true })} />);

    expect(screen.getByRole("status")).toHaveTextContent(/Context stale/i);
    expect(screen.getByRole("status")).toHaveTextContent(/server-provided refresh interval/i);
  });

  it("renders degraded reasons and evidence-backed suggestions", () => {
    const context = makeContext();
    context.overall.status = "degraded";
    context.overall.degradedReasons = ["Redis is unavailable; event delivery is process-local."];
    context.overall.checks = context.overall.checks.map((check) =>
      check.name === "redis"
        ? { ...check, status: "degraded", detail: "Redis is unavailable; event delivery is process-local." }
        : check,
    );
    context.cameras.online = 0;
    context.cameras.offline = 1;
    context.cameras.freshness = {
      observedAt: TIMESTAMP,
      status: "degraded",
      reason: "1 camera runtime state is offline.",
    };
    context.suggestions = [
      {
        suggestionId: "camera-runtime-camera-1",
        label: "Review camera Camera 1",
        reason: "Camera runtime status is offline.",
        evidence: [
          {
            kind: "health",
            id: "camera:camera-1",
            cameraId: "camera-1",
            occurredAt: TIMESTAMP,
            label: "camera runtime status",
            serverValidated: true,
            validatedAt: TIMESTAMP,
          },
        ],
        availability: "live",
        href: "/cameras",
      },
    ];

    render(<IntelligencePageContent state={makeState({ context })} />);

    expect(screen.queryByRole("heading", { name: /Degraded or unavailable signals/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.getByRole("dialog", { name: /Verified signals/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Redis is unavailable/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Review camera Camera 1/i })).toHaveAttribute("href", "/cameras");
    expect(screen.getByText(/Evidence: camera runtime status/i)).toBeInTheDocument();
  });

  it("renders an empty activity feed and no synthetic operational content", () => {
    const context = makeContext();
    render(<IntelligencePageContent state={makeState({ context })} />);

    expect(activityFromContext(context)).toEqual([]);
    expect(screen.getByTestId("aegis-voice-core")).toHaveTextContent("Voice Core: unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.getByTestId("activity-feed")).toHaveTextContent(/No alerts, events, or tracks were returned/i);
    expect(screen.getByText(/No evidence-backed suggestions were returned/i)).toBeInTheDocument();
    expect(screen.queryByText(/Export daily report/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Search security events/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^System Status$/i)).not.toBeInTheDocument();
  });

  it("keeps the command surface focused until operations are explicitly opened", () => {
    const { container } = render(<IntelligencePageContent state={makeState()} />);
    const pageShell = container.querySelector('[data-state="ready"]');

    expect(pageShell).toHaveClass("min-h-screen");
    expect(screen.getByTestId("aegis-voice-core")).toBeInTheDocument();
    expect(screen.queryByTestId("activity-feed")).not.toBeInTheDocument();
  });

  it("keeps a returned event's source freshness instead of substituting context generation time", () => {
    const context = makeContext();
    context.events = [
      {
        eventId: "event-1",
        summary: "Source-backed historical event",
        evidence: [
          {
            kind: "event",
            id: "event-1",
            occurredAt: "2026-07-30T11:55:00.000Z",
            label: "runtime event",
            serverValidated: true,
            validatedAt: TIMESTAMP,
          },
        ],
        freshness: {
          observedAt: "2026-07-30T11:55:00.000Z",
          status: "stale",
          reason: "Runtime event is older than the recent-event freshness policy.",
        },
      },
    ];

    expect(activityFromContext(context)).toEqual([
      expect.objectContaining({
        id: "event-event-1",
        observedAt: "2026-07-30T11:55:00.000Z",
        availability: "stale",
      }),
    ]);
  });

  it("does not present an unvalidated reference as recent evidence", () => {
    const context = makeContext();
    context.events = [
      {
        eventId: "event-without-validation",
        summary: "This source reference must not be shown as evidence.",
        evidence: [
          {
            kind: "event",
            id: "event-without-validation",
            occurredAt: TIMESTAMP,
            label: "unverified runtime event",
            serverValidated: false,
          },
        ],
        freshness: { observedAt: TIMESTAMP, status: "live" },
      },
    ];

    expect(activityFromContext(context)).toEqual([]);
  });

  it("renders the operational capability map and links only implemented pages", () => {
    const nodes = buildCapabilityNodes(makeContext());
    const linked = nodes.filter((node) => node.href);
    const operators = nodes.find((node) => node.id === "ops");

    expect(nodes.map((node) => node.label)).toEqual(
      expect.arrayContaining(["Cameras", "Tracking", "Risk", "Events", "Ops", "Evidence", "Semantic Search", "Memory", "Design", "Engineering"]),
    );
    expect(linked.map((node) => node.href)).toEqual(
      expect.arrayContaining(["/cameras", "/analytics", "/semantic", "/tracks", "/events"]),
    );
    expect(operators).toMatchObject({ availability: "unavailable" });
    expect(operators?.href).toBeUndefined();
    expect(nodes.some((node) => ["investigation", "incidents", "automation", "patrol", "knowledge"].includes(node.id))).toBe(false);
  });
});
