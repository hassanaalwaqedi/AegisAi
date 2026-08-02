import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AIOrb from "./AIOrb";

const canvasContext = {
  scale: vi.fn(),
  clearRect: vi.fn(),
  beginPath: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  fillStyle: "",
};

beforeEach(() => {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(canvasContext as unknown as CanvasRenderingContext2D);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("AIOrb", () => {
  it("exposes an accessible reduced-motion voice core state without inventing an audio waveform", async () => {
    render(
      <AIOrb
        contextStatus="live"
        voiceState="listening"
        microphoneLevel={0.62}
        playbackLevel={0}
        activeCapability="cameras"
        onActivate={vi.fn()}
        onListenToggle={vi.fn()}
        listeningEnabled
        voiceSessionActive={false}
      />,
    );

    const orb = screen.getByTestId("aegis-voice-orb");
    await waitFor(() => expect(orb).toHaveAttribute("data-reduced-motion", "true"));
    expect(orb).toHaveAttribute("data-voice-state", "listening");
    expect(orb).toHaveAttribute("data-active-capability", "cameras");
    expect(screen.getByRole("button", { name: /Aegis Voice Core/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask Aegis" })).toBeInTheDocument();
  });

  it("uses a single accessible control to stop an active listening session", () => {
    render(
      <AIOrb
        contextStatus="live"
        voiceState="listening"
        microphoneLevel={0}
        playbackLevel={0}
        onActivate={vi.fn()}
        onListenToggle={vi.fn()}
        listeningEnabled
        voiceSessionActive
      />,
    );

    expect(screen.getByRole("button", { name: "Stop listening" })).toBeInTheDocument();
  });
});
