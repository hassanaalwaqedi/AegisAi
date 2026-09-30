import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AegisIntelligenceNetwork } from "./aegis-intelligence-network";
import type { OperatorRuntime } from "@/lib/operator-runtime";

const runtime: OperatorRuntime = {
  state: "PRESENTING",
  activeGesture: "present-left",
  intent: "risk",
  projectionAnchor: "leftHandProjectionAnchor",
  attentionTarget: "left",
  listeningLevel: 0,
  speakingLevel: 0,
  target: "risk",
};

afterEach(cleanup);

describe("Aegis intelligence network", () => {
  it("focuses the real requested path after the network reaches READY", () => {
    const onCommand = vi.fn();
    render(<AegisIntelligenceNetwork runtime={runtime} activeDomain="events" metrics={{ risk: "1 active", cameras: "1/2 live" }} statuses={{ risk: "live", cameras: "live" }} signals={{ risk: [.82] }} bootStep={6} requestedNode="risk" onCommand={onCommand} />);

    expect(screen.getByRole("button", { name: /Risk\. 1 active\./ })).toHaveAttribute("data-active", "true");
    fireEvent.click(screen.getByRole("button", { name: /Cameras\. 1\/2 live\./ }));
    expect(onCommand).toHaveBeenCalledWith("Open camera", "cameras");
  });

  it("keeps command paths inactive during system check", () => {
    render(<AegisIntelligenceNetwork runtime={runtime} activeDomain="events" metrics={{ risk: "1 active" }} statuses={{ risk: "live" }} signals={{ risk: [.82] }} bootStep={0} requestedNode="risk" onCommand={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Risk\. 1 active\./ })).toHaveAttribute("data-active", "false");
    expect(screen.getByRole("status")).toHaveTextContent("SYSTEM CHECK");
  });
});
