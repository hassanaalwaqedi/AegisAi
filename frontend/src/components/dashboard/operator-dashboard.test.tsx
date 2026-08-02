import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { OperatorDashboard, operatorDashboardInternals } from "./operator-dashboard";
import type { Camera, RiskEvent, StatusResponse } from "@/types";

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
      status={readyStatus}
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
  it("uses operator-friendly priority copy and keeps technical data out of the main view", () => {
    renderDashboard();

    expect(screen.getByRole("heading", { name: "High priority" })).toBeInTheDocument();
    expect(screen.getByText("Immediate review recommended.")).toBeInTheDocument();
    expect(screen.queryByText("Frames Processed")).not.toBeInTheDocument();
    expect(screen.queryByText("GET /status")).not.toBeInTheDocument();
    expect(screen.queryByText("model-private-name")).not.toBeInTheDocument();
    expect(screen.queryByText("RAW_REASON_CODE")).not.toBeInTheDocument();
  });

  it("selects the highest-priority real camera and routes review actions to Camera Wall Focus", () => {
    renderDashboard();

    const review = screen.getAllByRole("link", { name: "Review" })[0];
    expect(review).toHaveAttribute("href", "/cameras?camera=camera-internal-2&view=focus");
    expect(screen.getByRole("heading", { name: "Camera 2" })).toBeInTheDocument();
    const openWallLinks = screen.getAllByRole("link", { name: /Open camera wall/i });
    expect(openWallLinks.some((link) => link.getAttribute("href") === "/cameras?camera=camera-internal-2&view=focus")).toBe(true);
  });

  it("derives review work and camera counts only from camera runtime and qualifying alerts", () => {
    const cameras = [makeCamera(1), makeCamera(2, "offline"), makeCamera(3, "reconnecting")];
    const items = operatorDashboardInternals.buildReviewItems(cameras, [
      { camera_id: "camera-internal-1", severity: "MEDIUM" },
      { camera_id: "camera-internal-1", severity: "LOW" },
    ]);
    const counts = operatorDashboardInternals.cameraCounts(cameras, items);

    expect(items.map((item) => item.camera.camera_id)).toEqual(expect.arrayContaining(["camera-internal-1", "camera-internal-2", "camera-internal-3"]));
    expect(counts).toEqual({ total: 3, live: 1, attention: 2, offline: 1 });
  });

  it("does not fabricate an all-clear state when no cameras are connected", () => {
    renderDashboard({ cameras: [], events: [] });

    expect(screen.getByRole("heading", { name: "No cameras connected" })).toBeInTheDocument();
    expect(screen.getByText("No cameras connected yet.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "All clear" })).not.toBeInTheDocument();
  });

  it("shows all-clear only with complete, live runtime data and no review work", () => {
    renderDashboard({ cameras: [makeCamera(1)], events: [] });
    expect(screen.getByRole("heading", { name: "All clear" })).toBeInTheDocument();
    expect(screen.getByText("No urgent activity needs review.")).toBeInTheDocument();
  });

  it("does not call a degraded service all-clear", () => {
    renderDashboard({ cameras: [makeCamera(1)], events: [], status: { system: { running: false } } as StatusResponse });
    expect(screen.getByRole("heading", { name: "Needs attention" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "All clear" })).not.toBeInTheDocument();
  });

  it("renders a truthful unavailable state with a real retry action and no fake counts", () => {
    const { onRetry } = renderDashboard({ cameras: [], events: [], isUnavailable: true });

    expect(screen.getByRole("heading", { name: "System unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Live camera data is temporarily unavailable.")).toBeInTheDocument();
    expect(screen.queryByText("0 total")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("uses skeletons without operational values while loading", () => {
    renderDashboard({ isLoading: true });
    expect(screen.getByLabelText("Loading security overview")).toBeInTheDocument();
    expect(screen.queryByText("All clear")).not.toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("keeps diagnostics collapsed until an operator explicitly opens it", () => {
    renderDashboard();
    const diagnostics = screen.getByText("Diagnostics").closest("details");
    expect(diagnostics).not.toHaveAttribute("open");
  });
});
