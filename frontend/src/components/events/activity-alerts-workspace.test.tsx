import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { ActivityAlertsWorkspace } from "./activity-alerts-workspace";
import { activityAlertsInternals } from "@/lib/activity-alerts";
import type { Camera, RiskEvent } from "@/types";

const liveCamera: Camera = {
  camera_id: "gate-2",
  name: "North Gate",
  location: "North entrance",
  source_type: "HTTP_STREAM",
  enabled: true,
  runtime: { camera_id: "gate-2", source_type: "HTTP_STREAM", status: "online", running: true, last_frame_time: "2026-07-31T20:59:50Z" },
};

const offlineCamera: Camera = {
  camera_id: "parking-1",
  name: "Parking East",
  source_type: "HTTP_STREAM",
  enabled: true,
  runtime: { camera_id: "parking-1", source_type: "HTTP_STREAM", status: "offline", running: false, last_frame_time: "2026-07-31T20:30:00Z" },
};

const highEvent: RiskEvent = {
  event_id: "event-9",
  camera_id: "gate-2",
  severity: "HIGH",
  timestamp: "2026-07-31T21:00:00Z",
  class_name: "vehicle",
  track_id: "track-private-8",
  model_source: ["model-private-name"],
  reason_codes: ["RAW_REASON_CODE"],
};

afterEach(cleanup);

describe("ActivityAlertsWorkspace", () => {
  it("uses operator wording and keeps technical payload fields hidden until Details opens", () => {
    render(<ActivityAlertsWorkspace cameras={[liveCamera]} events={[highEvent]} isLoading={false} isUnavailable={false} camerasUnavailable={false} onRetry={() => {}} />);

    expect(screen.getByRole("heading", { name: "Activity & Alerts" })).toBeInTheDocument();
    expect(screen.getAllByText("Vehicle activity needs review")).toHaveLength(2);
    expect(screen.queryByText("model-private-name")).not.toBeInTheDocument();
    expect(screen.queryByText("RAW_REASON_CODE")).not.toBeInTheDocument();
    const details = screen.getByText("Why did Aegis flag this?").closest("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle", { bubbles: true }));
    expect(screen.getByText("model-private-name")).toBeInTheDocument();
    expect(screen.getByText("RAW_REASON_CODE")).toBeInTheDocument();
  });

  it("selects review items and opens the exact Camera Wall Focus route", () => {
    render(<ActivityAlertsWorkspace cameras={[liveCamera, offlineCamera]} events={[highEvent]} isLoading={false} isUnavailable={false} camerasUnavailable={false} onRetry={() => {}} />);

    const queueItem = screen.getByRole("button", { name: /North Gate/i });
    queueItem.focus();
    expect(queueItem).toHaveFocus();
    fireEvent.click(queueItem);
    expect(screen.getByRole("heading", { name: "North Gate" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open camera/i })).toHaveAttribute("href", "/cameras?camera=gate-2&view=focus");
  });

  it("shows real camera-offline states without inventing visual evidence", () => {
    render(<ActivityAlertsWorkspace cameras={[offlineCamera]} events={[]} isLoading={false} isUnavailable={false} camerasUnavailable={false} onRetry={() => {}} />);

    expect(screen.getByText("Camera offline - check connection.")).toBeInTheDocument();
    expect(screen.queryByText("All clear")).not.toBeInTheDocument();
  });

  it("shows delayed and no-visual-evidence states from real runtime and event data", () => {
    const delayedCamera: Camera = { ...liveCamera, runtime: { ...liveCamera.runtime, status: "reconnecting", running: false } };
    const eventWithoutCamera: RiskEvent = { ...highEvent, event_id: "event-without-camera", camera_id: "not-returned-by-cameras" };
    const { rerender } = render(<ActivityAlertsWorkspace cameras={[delayedCamera]} events={[]} isLoading={false} isUnavailable={false} camerasUnavailable={false} onRetry={() => {}} />);
    expect(screen.getByText("Live image is delayed.")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();

    rerender(<ActivityAlertsWorkspace cameras={[]} events={[eventWithoutCamera]} isLoading={false} isUnavailable={false} camerasUnavailable={false} onRetry={() => {}} />);
    expect(screen.getByText("No visual evidence is available for this activity.")).toBeInTheDocument();
  });

  it("renders truthful empty and unavailable states with a real retry action", () => {
    const onRetry = vi.fn();
    const { rerender } = render(<ActivityAlertsWorkspace cameras={[]} events={[]} isLoading={false} isUnavailable={false} camerasUnavailable={false} onRetry={onRetry} />);
    expect(screen.getByText("Nothing needs review right now.")).toBeInTheDocument();
    rerender(<ActivityAlertsWorkspace cameras={[]} events={[]} isLoading={false} isUnavailable camerasUnavailable={false} onRetry={onRetry} />);
    expect(screen.getByText("Activity is temporarily unavailable.")).toBeInTheDocument();
    screen.getByRole("button", { name: "Retry" }).click();
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("suppresses low-value normal detections and prioritises the returned review work", () => {
    const lowEvent: RiskEvent = { event_id: "low-1", camera_id: "gate-2", severity: "LOW", timestamp: "2026-07-31T20:59:00Z", class_name: "person" };
    const items = activityAlertsInternals.buildActivityAlertItems([liveCamera, offlineCamera], [lowEvent, highEvent]);
    expect(items).toHaveLength(2);
    expect(items[0]?.status).toBe("high");
    expect(items.some((item) => item.event?.event_id === "low-1")).toBe(false);
  });
});
