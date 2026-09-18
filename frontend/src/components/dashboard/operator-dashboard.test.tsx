import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { OperatorDashboard, operatorDashboardInternals } from "./operator-dashboard";
import type { Camera, OperationalAlert, RiskEvent, StatusResponse } from "@/types";

function makeCamera(index: number, status: "online" | "offline" | "reconnecting" = "online"): Camera {
  return {
    camera_id: `camera-internal-${index}`,
    name: `Camera ${index}`,
    source_type: "HTTP_STREAM",
    enabled: true,
    runtime: {
      camera_id: `camera-internal-${index}`,
      source_type: "HTTP_STREAM",
      status,
      running: status === "online",
      last_frame_time: "2026-07-31T21:00:00Z",
    },
  };
}

const readyStatus = { system: { running: true } } as StatusResponse;
const criticalAlert: OperationalAlert = {
  alert_id: "alert-internal-9",
  event_id: "event-internal-9",
  risk_level: "CRITICAL",
  message: "Possible armed threat requires review.",
  camera_id: "camera-internal-2",
  timestamp: "2026-07-31T21:00:03Z",
  acknowledged: false,
};
const criticalEvent: RiskEvent = {
  event_id: "event-internal-9",
  camera_id: "camera-internal-2",
  severity: "CRITICAL",
  timestamp: "2026-07-31T21:00:03Z",
  model_source: ["model-private-name"],
  reason_codes: ["RAW_REASON_CODE"],
};

function renderDashboard(overrides: Partial<React.ComponentProps<typeof OperatorDashboard>> = {}) {
  const onRetry = vi.fn();
  render(
    <OperatorDashboard
      cameras={[makeCamera(1), makeCamera(2), makeCamera(3, "offline"), makeCamera(4, "reconnecting")]}
      events={[criticalEvent]}
      alerts={[criticalAlert]}
      incidents={[]}
      evidence={[]}
      status={readyStatus}
      availability={{ status: true, cameras: true, alerts: true, events: true, incidents: true, evidence: true }}
      isLoading={false}
      isUnavailable={false}
      onRetry={onRetry}
      {...overrides}
    />,
  );
  return { onRetry };
}

afterEach(cleanup);

describe("OperatorDashboard", () => {
  it("shows a concise attention-first overview without camera previews", () => {
    renderDashboard();

    expect(screen.getByRole("heading", { name: "Operational Overview" })).toBeInTheDocument();
    expect(screen.getByText("Current risk status and activity requiring attention.")).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("Active Alerts")).toBeInTheDocument();
    expect(screen.getByText("Open Incidents")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Needs Attention" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Latest Critical Activity" })).toBeInTheDocument();
    expect(screen.queryByText("Live view")).not.toBeInTheDocument();
    expect(screen.queryByText("Camera overview")).not.toBeInTheDocument();
    expect(screen.queryByText("model-private-name")).not.toBeInTheDocument();
    expect(screen.queryByText("RAW_REASON_CODE")).not.toBeInTheDocument();
  });

  it("routes reviews to the dedicated camera and events pages", () => {
    renderDashboard();

    const reviewLinks = screen.getAllByRole("link", { name: "Review" });
    expect(reviewLinks.some((link) => link.getAttribute("href") === "/events")).toBe(true);
    expect(reviewLinks.some((link) => link.getAttribute("href") === "/cameras?camera=camera-internal-3&view=focus")).toBe(true);
    expect(screen.getByRole("link", { name: "Open Camera Wall" })).toHaveAttribute("href", "/cameras");
    expect(screen.getByRole("link", { name: "Search Evidence" })).toHaveAttribute("href", "/semantic");
  });

  it("derives attention from real alerts and camera runtime status", () => {
    const cameras = [makeCamera(1), makeCamera(2, "offline"), makeCamera(3, "reconnecting")];
    const items = operatorDashboardInternals.buildAttentionItems({
      cameras,
      alerts: [criticalAlert],
      events: [],
      incidents: [],
      status: readyStatus,
      availability: { status: true, cameras: true, alerts: true, events: true, incidents: true, evidence: true },
    });
    const counts = operatorDashboardInternals.cameraCounts(cameras);

    expect(items.map((item) => item.kind)).toEqual(expect.arrayContaining(["alert", "camera"]));
    expect(counts).toEqual({ total: 3, live: 1, attention: 1, offline: 1 });
  });

  it("shows unavailable rather than fabricated values when a source cannot be loaded", () => {
    renderDashboard({
      alerts: undefined,
      incidents: undefined,
      evidence: undefined,
      availability: { status: true, cameras: true, alerts: false, events: true, incidents: false, evidence: false },
      isUnavailable: true,
    });

    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
  });

  it("uses skeletons without operational values while loading", () => {
    renderDashboard({ isLoading: true });
    expect(screen.getByLabelText("Loading operational overview")).toBeInTheDocument();
    expect(screen.queryByText("Critical alert")).not.toBeInTheDocument();
  });
});
