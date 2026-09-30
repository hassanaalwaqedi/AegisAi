import { describe, expect, it } from "vitest";

import { createOperatorRuntime, gestureFor, operatorState, projectionAnchorFor } from "./operator-runtime";
import type { OperatorExecution } from "./operator-api";

const cameraExecution: OperatorExecution = {
  action: "CAMERA_OPEN",
  intent: "CAMERA",
  answer: "Opening Camera 2.",
  panel: "camera",
  result: { camera: { camera_id: "camera-2" } },
  sources: [],
  trace: [],
  response_language: "English",
};

const base = {
  voiceState: "off" as const,
  microphoneActive: false,
  commandPending: false,
  toolPending: false,
  execution: null,
  activeDomain: null,
  warning: false,
  error: null,
  listeningLevel: 0,
  speakingLevel: 0,
};

describe("OperatorController runtime", () => {
  it("does not invent listening when a voice session is merely open", () => {
    expect(operatorState({ ...base, voiceState: "listening" })).toBe("IDLE");
    expect(operatorState({ ...base, voiceState: "listening", microphoneActive: true })).toBe("LISTENING");
  });

  it("uses actual voice and backend lifecycles in priority order", () => {
    expect(operatorState({ ...base, voiceState: "thinking" })).toBe("THINKING");
    expect(operatorState({ ...base, commandPending: true })).toBe("EXECUTING");
    expect(operatorState({ ...base, execution: cameraExecution })).toBe("PRESENTING");
    expect(operatorState({ ...base, voiceState: "speaking", commandPending: true })).toBe("SPEAKING");
    expect(operatorState({ ...base, voiceState: "error", execution: cameraExecution })).toBe("ERROR");
  });

  it("maps real camera work to a right-hand gesture and rig anchor", () => {
    const runtime = createOperatorRuntime({ ...base, commandPending: true, activeDomain: "cameras" });
    expect(runtime.activeGesture).toBe("summon-right");
    expect(runtime.projectionAnchor).toBe("rightHandProjectionAnchor");
    expect(runtime.target).toBeNull();
    expect(gestureFor("PRESENTING", "risk")).toBe("present-left");
    expect(projectionAnchorFor("evidence")).toBe("rightHandProjectionAnchor");
  });

  it("keeps the exact requested module available to motion and navigation", () => {
    const runtime = createOperatorRuntime({ ...base, commandPending: true, activeDomain: "events", target: "semantic" });
    expect(runtime.target).toBe("semantic");
    expect(runtime.intent).toBe("evidence");
  });

  it("only exposes mouth-driving amplitude during real PCM playback", () => {
    expect(createOperatorRuntime({ ...base, speakingLevel: 0.8 }).speakingLevel).toBe(0);
    expect(createOperatorRuntime({ ...base, voiceState: "speaking", speakingLevel: 0.8 }).speakingLevel).toBe(0.8);
    expect(createOperatorRuntime({ ...base, voiceState: "speaking", speakingLevel: 0.8 }).listeningLevel).toBe(0);
  });
});
