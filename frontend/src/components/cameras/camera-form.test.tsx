import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@/hooks/use-aegis-api", async () => {
  const React = await import("react");
  const successfulTest = {
    ok: true,
    status: "online" as const,
    test_id: "test-proof-1",
    masked_url: "rtsp://****@192.168.1.20:554/stream1",
    dns_resolved: true,
    host_reachable: true,
    time_to_first_frame_ms: 42,
    width: 1920,
    height: 1080,
  };
  return {
    useCreateCameraMutation: () => ({ isPending: false, mutateAsync: vi.fn() }),
    useUploadVideoMutation: () => ({ isPending: false, mutateAsync: vi.fn() }),
    useProcessVideoMutation: () => ({ isPending: false, mutateAsync: vi.fn() }),
    useCameraConnectionTestMutation: () => {
      const [data, setData] = React.useState<typeof successfulTest | undefined>();
      return {
        data,
        error: null,
        isPending: false,
        reset: () => setData(undefined),
        mutateAsync: async () => setData(successfulTest),
      };
    },
  };
});

import { CameraForm, cameraFormInternals } from "./camera-form";

afterEach(() => cleanup());

describe("CameraForm RTSP V2", () => {
  it("reports rejected YouTube media without claiming camera sign-in failed", () => {
    const t = (key: string) => key;
    const result = { ok: false, error_category: "youtube_media_unavailable" };

    expect(cameraFormInternals.connectionTestMessage(result, t)).toBe("conn_msg_youtube_media");
    expect(cameraFormInternals.connectionTestResultLabel(result, t)).toBe("conn_lbl_youtube");
  });

  it("clears a successful connection proof when the RTSP source changes", async () => {
    render(<CameraForm />);

    fireEvent.change(screen.getByLabelText("Source type"), { target: { value: "RTSP_STREAM" } });
    const host = screen.getByLabelText("Host / IP");
    fireEvent.change(host, { target: { value: "192.168.1.20" } });
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));

    expect(await screen.findByText("Connection verified")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save camera" })).toBeEnabled();

    fireEvent.change(host, { target: { value: "192.168.1.21" } });

    await waitFor(() => expect(screen.queryByText("Connection verified")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Save camera" })).toBeDisabled();
  });

  it("conceals advanced full RTSP URLs and permits explicit disabled saves", () => {
    render(<CameraForm />);

    fireEvent.change(screen.getByLabelText("Source type"), { target: { value: "RTSP_STREAM" } });
    fireEvent.click(screen.getByLabelText("Advanced full URL"));
    expect(screen.getByPlaceholderText("rtsp://username:password@host:554/stream")).toHaveAttribute("type", "password");

    fireEvent.click(screen.getByLabelText("Save as disabled / unverified"));
    expect(screen.getByRole("button", { name: "Save disabled camera" })).toBeEnabled();
  });
});
