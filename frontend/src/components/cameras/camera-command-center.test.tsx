import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

const testState = vi.hoisted(() => ({
  detections: [] as any[],
  events: [] as any[],
  eventsError: false,
  startCamera: vi.fn(),
  stopCamera: vi.fn(),
  updateCamera: vi.fn(),
}));

vi.mock("@/hooks/use-aegis-api", () => ({
  useCameraDetectionsQuery: () => ({ data: { detections: testState.detections }, isLoading: false, isError: false }),
  useCameraEventsQuery: () => ({ data: { events: testState.events }, isLoading: false, isError: testState.eventsError, error: new Error("diagnostic detail") }),
  useCameraOverlaysQuery: () => ({ data: { zones: [], heatmap: [] } }),
  useStartCameraMutation: () => ({ isPending: false, mutateAsync: testState.startCamera }),
  useStopCameraMutation: () => ({ isPending: false, mutateAsync: testState.stopCamera }),
  useUpdateCameraMutation: () => ({ isPending: false, mutateAsync: testState.updateCamera }),
}));

import { CameraCommandCenter, cameraCommandCenterInternals, overlayLabel } from "./camera-command-center";

const camera = {
  camera_id: "main-road-cam-001",
  name: "Main Road Camera",
  source_type: "HTTP_STREAM" as const,
  enabled: true,
  runtime: { camera_id: "main-road-cam-001", source_type: "HTTP_STREAM" as const, status: "online" as const, running: true, fps: 24, width: 1920, height: 1080, last_frame_time: "2026-07-30T21:00:00Z" },
};

class MockWebSocket {
  static created = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  constructor(_: string) {
    MockWebSocket.created += 1;
  }
}

beforeEach(() => {
  testState.detections = [
    { track_id: "person-raw-9", class_name: "person", is_person: true, confidence: 0.82 },
    { track_id: "car-raw-2", class_name: "car", confidence: 0.72 },
  ];
  testState.events = [];
  testState.eventsError = false;
  testState.startCamera.mockReset().mockResolvedValue(undefined);
  testState.stopCamera.mockReset().mockResolvedValue(undefined);
  testState.updateCamera.mockReset().mockResolvedValue(undefined);
  MockWebSocket.created = 0;
  vi.stubGlobal("WebSocket", MockWebSocket);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CameraCommandCenter", () => {
  it("renders a compact signals panel and dominant camera hero without a review queue", () => {
    render(<CameraCommandCenter camera={camera} />);

    expect(screen.getByRole("heading", { name: "Live Signals" })).toBeInTheDocument();
    expect(screen.getByText("People").parentElement).toHaveTextContent("1");
    expect(screen.getByText("Vehicles").parentElement).toHaveTextContent("1");
    expect(screen.getAllByText("Online").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Clear").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Main Road Camera" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Main Road Camera live preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View detections" })).toBeInTheDocument();
    expect(screen.queryByText("Review queue")).not.toBeInTheDocument();
    expect(screen.queryByText("No activity to review.")).not.toBeInTheDocument();
  });

  it("shows only the latest short signal and keeps raw evidence fields out of Focus Mode", () => {
    testState.events = [{
      event_id: "event-raw-42", track_id: "track-raw-77", timestamp: "2026-07-30T21:00:00Z", severity: "warning",
      object_class: "bus", model_source: ["yolo11n.pt"], reason_codes: ["REAL_OBJECT_DETECTION"], confidence: 0.87,
    }];
    render(<CameraCommandCenter camera={camera} />);

    expect(screen.getByText("Latest signal")).toBeInTheDocument();
    expect(screen.getByText("Bus needs attention")).toBeInTheDocument();
    expect(screen.queryByText("yolo11n.pt")).not.toBeInTheDocument();
    expect(screen.queryByText("REAL_OBJECT_DETECTION")).not.toBeInTheDocument();
    expect(screen.queryByText("track-raw-77")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "View details" })).not.toBeInTheDocument();
  });

  it("shows a concise truthful offline state", () => {
    render(<CameraCommandCenter camera={{ ...camera, camera_id: "http-stream-tiwfw7", name: "HTTP Stream", runtime: { ...camera.runtime, status: "offline", running: false } }} />);

    expect(screen.getByRole("heading", { name: "Camera Tiwfw7" })).toBeInTheDocument();
    expect(screen.getAllByText("Offline").length).toBeGreaterThan(0);
    expect(screen.getByText("Monitoring unavailable")).toBeInTheDocument();
    expect(MockWebSocket.created).toBe(0);
    expect(screen.getAllByText("Camera offline - check connection.").length).toBeGreaterThan(0);
  });

  it("uses the authenticated snapshot preview when a browser WebSocket is not configured", () => {
    render(<CameraCommandCenter camera={camera} />);

    const preview = screen.getByRole("img", { name: "Main Road Camera live preview" });
    expect(preview).toHaveAttribute("src", "/api/backend/cameras/main-road-cam-001/snapshot?preview=0");
    fireEvent.load(preview);
    expect(screen.getAllByText("Online").length).toBeGreaterThan(0);
  });

  it("allows each fallback snapshot enough time to load before requesting the next one", () => {
    vi.useFakeTimers();
    render(<CameraCommandCenter camera={camera} />);

    const preview = screen.getByRole("img", { name: "Main Road Camera live preview" });
    expect(preview).toHaveAttribute("src", "/api/backend/cameras/main-road-cam-001/snapshot?preview=0");

    act(() => vi.advanceTimersByTime(499));
    expect(preview).toHaveAttribute("src", "/api/backend/cameras/main-road-cam-001/snapshot?preview=0");

    act(() => vi.advanceTimersByTime(1));
    expect(preview).toHaveAttribute("src", "/api/backend/cameras/main-road-cam-001/snapshot?preview=1");
  });

  it("keeps the Focus Mode action dock wired to existing camera controls", () => {
    const openWindow = vi.spyOn(window, "open").mockImplementation(() => null);
    render(<CameraCommandCenter camera={camera} />);

    const detections = screen.getByRole("button", { name: "View detections" });
    expect(detections).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(detections);
    expect(detections).toHaveAttribute("aria-pressed", "false");

    const zones = screen.getByRole("button", { name: "Zones" });
    fireEvent.click(zones);
    expect(zones).toHaveAttribute("aria-pressed", "true");

    const heatmap = screen.getByRole("button", { name: "Heatmap" });
    fireEvent.click(heatmap);
    expect(heatmap).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "Snapshot" }));
    expect(openWindow).toHaveBeenCalledWith("/api/backend/cameras/main-road-cam-001/snapshot", "_blank", "noopener,noreferrer");

    const cameraPanel = document.querySelector<HTMLElement>('[aria-labelledby="selected-camera-title"]');
    const requestFullscreen = vi.fn();
    Object.defineProperty(cameraPanel, "requestFullscreen", { configurable: true, value: requestFullscreen });
    fireEvent.click(screen.getByRole("button", { name: "Fullscreen" }));
    expect(requestFullscreen).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(testState.stopCamera).toHaveBeenCalledWith("main-road-cam-001");
  });

  it("formats clean overlay labels without a track identifier", () => {
    expect(overlayLabel({ class_name: "bus", confidence: 0.87 })).toBe("Bus 87%");
    expect(overlayLabel({ class_name: "person", confidence: undefined })).toBe("Person");
  });

  it("renders one current detection per tracked object", () => {
    const current = cameraCommandCenterInternals.filterCurrentDetections([
      { track_id: "cam-1:7", class_name: "person", frame_id: 41, confidence: 0.91 },
      { track_id: "cam-1:7", class_name: "person", frame_id: 42, confidence: 0.93 },
      { track_id: "cam-1:8", class_name: "person", frame_id: 42, confidence: 0.88 },
      { track_id: "cam-1:8", class_name: "person", frame_id: 42, confidence: 0.89 },
    ]);

    expect(current).toHaveLength(2);
    expect(current.map((item) => item.track_id)).toEqual(["cam-1:7", "cam-1:8"]);
    expect(current[1]?.confidence).toBe(0.89);
  });

  it("removes detections that no longer describe the live frame", () => {
    const current = cameraCommandCenterInternals.filterCurrentDetections(
      [{ track_id: "cam-1:7", class_name: "person", frame_id: 42, last_seen: "2026-09-16T19:21:03.000000" }],
      Date.parse("2026-09-16T19:21:10Z"),
    );

    expect(current).toEqual([]);
  });

  it("keeps high-priority evidence while grouping repeated routine activity", () => {
    const activity = cameraCommandCenterInternals.buildRecentActivity([
      { event_id: "car-1", class_name: "car", severity: "LOW", timestamp: "2026-07-30T21:00:00Z" },
      { event_id: "car-2", class_name: "car", severity: "LOW", timestamp: "2026-07-30T21:01:00Z" },
      { event_id: "person-1", class_name: "person", severity: "LOW", timestamp: "2026-07-30T21:02:00Z" },
      { event_id: "high-1", class_name: "car", severity: "HIGH", timestamp: "2026-07-30T21:03:00Z" },
    ]);

    expect(activity.map((event) => event.event_id)).toEqual(["high-1", "person-1", "car-2"]);
  });
});
