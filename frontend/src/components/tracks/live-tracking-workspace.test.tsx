import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { LiveTrackingWorkspace } from "./live-tracking-workspace";
import { liveTrackingInternals } from "@/lib/live-tracking";
import type { Camera, Track } from "@/types";

const liveCamera: Camera = {
  camera_id: "north-gate",
  name: "North Gate",
  location: "North entrance",
  source_type: "HTTP_STREAM",
  enabled: true,
  runtime: {
    camera_id: "north-gate",
    source_type: "HTTP_STREAM",
    status: "online",
    running: true,
    last_frame_time: "2026-07-31T20:59:50Z",
  },
};

const personTrack: Track = {
  track_id: "person-internal-1",
  class_name: "person",
  is_person: true,
  camera_id: "north-gate",
  movement_state: "moving",
  first_seen: "2026-07-31T20:58:00Z",
  last_seen: "2026-07-31T21:00:00Z",
  risk_level: "LOW",
};

const vehicleTrack: Track = {
  track_id: "vehicle-internal-2",
  class_name: "car",
  is_vehicle: true,
  camera_id: "north-gate",
  movement_state: "stationary",
  last_seen: "2026-07-31T21:00:01Z",
  risk_level: "HIGH",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LiveTrackingWorkspace", () => {
  it("uses returned tracks and camera links for the operator view without exposing internal values by default", () => {
    render(<LiveTrackingWorkspace tracks={[personTrack, vehicleTrack]} cameras={[liveCamera]} isLoading={false} isUnavailable={false} camerasUnavailable={false} onRetry={() => {}} />);

    expect(screen.getByRole("heading", { name: "Live Tracking" })).toBeInTheDocument();
    expect(screen.getByText("Objects tracked now").parentElement).toHaveTextContent("2");
    expect(screen.getByRole("heading", { name: "Person" })).toBeInTheDocument();
    expect(screen.getAllByText("North Gate").length).toBeGreaterThan(0);
    expect(screen.queryByText("person-internal-1")).not.toBeInTheDocument();
    expect(screen.queryByText("vehicle-internal-2")).not.toBeInTheDocument();

    const details = screen.getByText("Details").closest("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle", { bubbles: true }));
    expect(screen.getByText("person-internal-1")).toBeInTheDocument();
  });

  it("filters by object category, selects an item, and opens its real camera focus route", () => {
    render(<LiveTrackingWorkspace tracks={[personTrack, vehicleTrack]} cameras={[liveCamera]} isLoading={false} isUnavailable={false} camerasUnavailable={false} onRetry={() => {}} />);

    fireEvent.click(screen.getByRole("tab", { name: "Vehicles" }));
    expect(screen.queryByRole("button", { name: /Person.*North Gate/i })).not.toBeInTheDocument();
    const vehicle = screen.getByRole("button", { name: /Vehicle.*North Gate/i });
    fireEvent.click(vehicle);
    expect(screen.getByRole("heading", { name: "Vehicle" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open camera/i })).toHaveAttribute("href", "/cameras?camera=north-gate&view=focus");
  });

  it("renders delayed, offline, no-preview, empty, and unavailable states without invented live activity", () => {
    const delayedCamera: Camera = { ...liveCamera, runtime: { ...liveCamera.runtime, status: "reconnecting", running: false } };
    const noCameraTrack: Track = { ...personTrack, track_id: "unlinked-track", camera_id: undefined };
    const { rerender } = render(<LiveTrackingWorkspace tracks={[personTrack]} cameras={[delayedCamera]} isLoading={false} isUnavailable={false} camerasUnavailable={false} onRetry={() => {}} />);
    expect(screen.getAllByText("Live image delayed").length).toBeGreaterThan(0);

    rerender(<LiveTrackingWorkspace tracks={[noCameraTrack]} cameras={[]} isLoading={false} isUnavailable={false} camerasUnavailable={false} onRetry={() => {}} />);
    expect(screen.getByText("No preview available")).toBeInTheDocument();

    rerender(<LiveTrackingWorkspace tracks={[]} cameras={[]} isLoading={false} isUnavailable={false} camerasUnavailable={false} onRetry={() => {}} />);
    expect(screen.getByText("No tracked activity matches this view.")).toBeInTheDocument();

    const onRetry = vi.fn();
    rerender(<LiveTrackingWorkspace tracks={[]} cameras={[]} isLoading={false} isUnavailable camerasUnavailable={false} onRetry={onRetry} />);
    expect(screen.getByText("Live tracking is temporarily unavailable.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("classifies only supplied backend state and preserves unavailable movement", () => {
    const unknownTrack: Track = { track_id: "unknown", class_name: "private-class", camera_id: "north-gate" };
    const items = liveTrackingInternals.buildLiveTrackingItems([personTrack, vehicleTrack, unknownTrack], [liveCamera]);

    expect(items.map((item) => item.label)).toEqual(["Person", "Vehicle", "Tracked object"]);
    expect(items[0]?.movementLabel).toBe("Moving");
    expect(items[2]?.movementLabel).toBe("Information unavailable");
    expect(items[1]?.riskLabel).toBe("High priority");
  });
});
