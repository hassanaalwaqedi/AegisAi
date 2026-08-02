import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

vi.mock("@/components/cameras/camera-command-center", () => ({
  CameraCommandCenter: ({ camera }: { camera: { name?: string } }) => <div>Focused player: {camera.name}</div>,
}));

import { CameraPreview, CameraWall, cameraWallInternals } from "./camera-wall";

class MockIntersectionObserver {
  constructor(private readonly callback: IntersectionObserverCallback) {}
  observe = () => this.callback([{ isIntersecting: true } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
  disconnect = vi.fn();
  unobserve = vi.fn();
  takeRecords = vi.fn(() => []);
  root = null;
  rootMargin = "";
  thresholds = [];
}

const camera = (index: number, status: "online" | "offline" | "reconnecting" = "online") => ({
  camera_id: `camera-internal-${index}`,
  name: `Camera ${index}`,
  source_type: "HTTP_STREAM" as const,
  enabled: true,
  runtime: { camera_id: `camera-internal-${index}`, source_type: "HTTP_STREAM" as const, status, running: status === "online", last_frame_time: "2026-07-30T21:00:00Z" },
});

const cameras = [
  ...Array.from({ length: 7 }, (_, index) => camera(index + 1)),
  camera(8, "offline"),
  camera(9, "reconnecting"),
  camera(10),
];

function renderWall(overrides: Partial<React.ComponentProps<typeof CameraWall>> = {}) {
  const onViewChange = vi.fn();
  const onCameraChange = vi.fn();
  const result = render(<CameraWall cameras={cameras} events={[{ camera_id: "camera-internal-2", severity: "MEDIUM", event_id: "event-raw", model_source: ["yolo11n.pt"] }]} initialView="grid" initialCameraId="camera-internal-1" systemStatus="connected" onViewChange={onViewChange} onCameraChange={onCameraChange} {...overrides} />);
  return { ...result, onViewChange, onCameraChange };
}

beforeEach(() => {
  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CameraWall", () => {
  it("defaults to Grid mode and renders no more than nine real camera tiles", () => {
    renderWall();

    expect(screen.getByRole("button", { name: "Grid" })).toBeInTheDocument();
    expect(document.querySelectorAll("[data-camera-tile]")).toHaveLength(9);
    expect(screen.getByText("10 cameras")).toBeInTheDocument();
    expect(screen.getByText("Selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Camera 1 in Focus mode" })).toHaveClass("border-signal-cyan");
    expect(screen.queryByText("camera-internal-1")).not.toBeInTheDocument();
    expect(screen.queryByText("yolo11n.pt")).not.toBeInTheDocument();
  });

  it("paginates instead of adding a vertically scrolling tenth card", () => {
    renderWall();
    expect(screen.getByText("1–9 of 10")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(document.querySelectorAll("[data-camera-tile]")).toHaveLength(1);
    expect(screen.getByText("10–10 of 10")).toBeInTheDocument();
  });

  it("filters and searches using real camera runtime status and names", () => {
    renderWall();
    fireEvent.click(screen.getByRole("button", { name: /Offline 1/i }));
    expect(document.querySelectorAll("[data-camera-tile]")).toHaveLength(1);
    expect(screen.getAllByText("Camera 8").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /All cameras 10/i }));
    fireEvent.change(screen.getByRole("textbox", { name: "Search cameras" }), { target: { value: "Camera 10" } });
    expect(document.querySelectorAll("[data-camera-tile]")).toHaveLength(1);
    expect(screen.getByText("Camera 10")).toBeInTheDocument();
  });

  it("opens focus mode and makes review queue actions select the real camera", () => {
    const { onCameraChange, onViewChange } = renderWall();
    fireEvent.click(screen.getByRole("button", { name: /Open Camera 2 in Focus mode/i }));
    expect(onCameraChange).toHaveBeenCalledWith("camera-internal-2");
    expect(onViewChange).toHaveBeenCalledWith("focus");
    expect(screen.getByText("Focused player: Camera 2")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Review" })[0]);
    expect(onViewChange).toHaveBeenCalledWith("focus");
  });

  it("honours a URL-backed Focus selection on initial render", () => {
    renderWall({ initialView: "focus", initialCameraId: "camera-internal-4" });
    expect(screen.getByText("Focused player: Camera 4")).toBeInTheDocument();
  });

  it("returns from Focus to Grid and switches the real selected camera from its thumbnail rail", () => {
    const { onCameraChange } = renderWall();
    fireEvent.click(screen.getByRole("button", { name: /Open Camera 2 in Focus mode/i }));
    fireEvent.click(screen.getByRole("button", { name: "Camera 3" }));
    expect(onCameraChange).toHaveBeenCalledWith("camera-internal-3");
    expect(screen.getByText("Focused player: Camera 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Back to grid/i }));
    expect(document.querySelectorAll("[data-camera-tile]")).toHaveLength(9);
  });

  it("supports arrow-key navigation between visible camera tiles", () => {
    renderWall();
    const [first, second] = screen.getAllByRole("button", { name: /Open Camera .* in Focus mode/i });
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(document.activeElement).toBe(second);
  });

  it("shows an unavailable Map state rather than a decorative map without coordinates", () => {
    renderWall({ initialView: "map" });
    expect(screen.getByText("Camera locations are not configured yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Map" })).toBeDisabled();
  });

  it("uses snapshots only while visible and releases the refresh timer on unmount", () => {
    vi.useFakeTimers();
    const clearTimer = vi.spyOn(window, "clearInterval");
    const { unmount } = render(<CameraPreview camera={camera(1)} status="live" />);
    expect(document.querySelector("img")).toBeInTheDocument();
    unmount();
    expect(clearTimer).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("shows the real delayed-frame state instead of presenting a reconnecting camera as live", () => {
    render(<CameraPreview camera={camera(9, "reconnecting")} status="attention" />);
    expect(screen.getByText("Live image is delayed.")).toBeInTheDocument();
    expect(document.querySelector("img")).not.toBeInTheDocument();
  });

  it("derives review work from offline cameras and medium-or-higher events only", () => {
    const items = cameraWallInternals.buildReviewItems(cameras, [
      { camera_id: "camera-internal-2", severity: "MEDIUM" },
      { camera_id: "camera-internal-3", severity: "LOW" },
    ]);
    expect(items.map((item) => item.camera.camera_id)).toEqual(expect.arrayContaining(["camera-internal-2", "camera-internal-8"]));
    expect(items.map((item) => item.camera.camera_id)).not.toContain("camera-internal-3");
  });

  it("uses a readable operator label when a source type was used as the camera name", () => {
    expect(cameraWallInternals.cameraDisplayName({ ...camera(1), camera_id: "http-stream-tiwfw7", name: "HTTP Stream" })).toBe("Camera Tiwfw7");
  });
});
