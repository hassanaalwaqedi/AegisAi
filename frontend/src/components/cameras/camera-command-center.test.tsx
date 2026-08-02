import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

const testState = vi.hoisted(() => ({
  detections: [] as any[],
  events: [] as any[],
  eventsError: false,
}));

vi.mock("@/hooks/use-aegis-api", () => ({
  useCameraDetectionsQuery: () => ({ data: { detections: testState.detections }, isLoading: false, isError: false }),
  useCameraEventsQuery: () => ({ data: { events: testState.events }, isLoading: false, isError: testState.eventsError, error: new Error("diagnostic detail") }),
  useCameraOverlaysQuery: () => ({ data: { zones: [], heatmap: [] } }),
  useStartCameraMutation: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useStopCameraMutation: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useUpdateCameraMutation: () => ({ isPending: false, mutateAsync: vi.fn() }),
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
  MockWebSocket.created = 0;
  vi.stubGlobal("WebSocket", MockWebSocket);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CameraCommandCenter", () => {
  it("renders calm operator-facing live activity and no activity state", () => {
    render(<CameraCommandCenter camera={camera} />);

    expect(screen.getByRole("heading", { name: "Happening now" })).toBeInTheDocument();
    expect(screen.getByText("Live activity")).toBeInTheDocument();
    expect(screen.getAllByText("Recent activity")).toHaveLength(2);
    expect(screen.getByText("No activity to review.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View detections" })).toBeInTheDocument();
    expect(screen.queryByText("Detection Load")).not.toBeInTheDocument();
    expect(screen.queryByText("Active tracks")).not.toBeInTheDocument();
  });

  it("keeps raw evidence fields out of the main activity card until details are requested", () => {
    testState.events = [{
      event_id: "event-raw-42", track_id: "track-raw-77", timestamp: "2026-07-30T21:00:00Z", severity: "warning",
      object_class: "bus", model_source: ["yolo11n.pt"], reason_codes: ["REAL_OBJECT_DETECTION"], confidence: 0.87,
    }];
    render(<CameraCommandCenter camera={camera} />);

    expect(screen.getByText("Bus needs attention")).toBeInTheDocument();
    expect(screen.queryByText("yolo11n.pt")).not.toBeInTheDocument();
    expect(screen.queryByText("REAL_OBJECT_DETECTION")).not.toBeInTheDocument();
    expect(screen.queryByText("track-raw-77")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "View details" }));
    expect(screen.getByText("Why did Aegis flag this?")).toBeInTheDocument();
    expect(screen.getByText("yolo11n.pt")).toBeInTheDocument();
    expect(screen.getByText("REAL_OBJECT_DETECTION")).toBeInTheDocument();
  });

  it("shows a concise truthful offline state", () => {
    render(<CameraCommandCenter camera={{ ...camera, camera_id: "http-stream-tiwfw7", name: "HTTP Stream", runtime: { ...camera.runtime, status: "offline", running: false } }} />);

    expect(screen.getByRole("heading", { name: "Camera Tiwfw7" })).toBeInTheDocument();
    expect(screen.getAllByText("Camera offline")).toHaveLength(2);
    expect(screen.queryByText("Live camera")).not.toBeInTheDocument();
    expect(MockWebSocket.created).toBe(0);
    expect(screen.getAllByText("Camera offline - check connection.").length).toBeGreaterThan(0);
  });

  it("uses the authenticated snapshot preview when a browser WebSocket is not configured", () => {
    render(<CameraCommandCenter camera={camera} />);

    const preview = screen.getByRole("img", { name: "Main Road Camera live preview" });
    expect(preview).toHaveAttribute("src", "/api/backend/cameras/main-road-cam-001/snapshot?preview=0");
    fireEvent.load(preview);
    expect(screen.getByText("Live monitoring")).toBeInTheDocument();
  });

  it("formats clean overlay labels without a track identifier", () => {
    expect(overlayLabel({ class_name: "bus", confidence: 0.87 })).toBe("Bus 87%");
    expect(overlayLabel({ class_name: "person", confidence: undefined })).toBe("Person");
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
