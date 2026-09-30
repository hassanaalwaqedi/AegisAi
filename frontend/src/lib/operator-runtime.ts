import type { OperatorExecution } from "./operator-api";
import type { AegisVoiceSessionState, VoiceState } from "./live-voice";

/**
 * The one authoritative state of the embodied operator.  These values are
 * intentionally event-derived: no timeout is allowed to manufacture a
 * listening, speaking, or command-execution transition.
 */
export const OPERATOR_STATES = [
  "IDLE",
  "LISTENING",
  "THINKING",
  "SPEAKING",
  "EXECUTING",
  "PRESENTING",
  "WARNING",
  "ERROR",
] as const;

export type OperatorState = (typeof OPERATOR_STATES)[number];

export const OPERATOR_GESTURES = [
  "idle",
  "listen",
  "think",
  "speak-neutral",
  "present-left",
  "present-right",
  "point-left",
  "point-right",
  "summon-left",
  "summon-right",
  "push-forward",
  "warning-attention",
  "dismiss",
] as const;

export type OperatorGesture = (typeof OPERATOR_GESTURES)[number];
export type ProjectionAnchorName =
  | "rightHandProjectionAnchor"
  | "leftHandProjectionAnchor"
  | "rightSideProjectionAnchor"
  | "leftSideProjectionAnchor"
  | "centerProjectionAnchor";

export type ProjectionAnchor = {
  x: number;
  y: number;
  /** `true` only when the position was read from a loaded skeleton bone. */
  fromRig: boolean;
};

export type OperatorAssetStatus = "checking" | "ready" | "missing" | "error";

export const DEFAULT_PROJECTION_ANCHORS: Record<ProjectionAnchorName, ProjectionAnchor> = {
  rightHandProjectionAnchor: { x: 65, y: 54, fromRig: false },
  leftHandProjectionAnchor: { x: 35, y: 54, fromRig: false },
  rightSideProjectionAnchor: { x: 76, y: 48, fromRig: false },
  leftSideProjectionAnchor: { x: 24, y: 48, fromRig: false },
  centerProjectionAnchor: { x: 50, y: 48, fromRig: false },
};

export function defaultProjectionAnchors(): Record<ProjectionAnchorName, ProjectionAnchor> {
  return Object.fromEntries(Object.entries(DEFAULT_PROJECTION_ANCHORS).map(([name, anchor]) => [name, { ...anchor }])) as Record<ProjectionAnchorName, ProjectionAnchor>;
}

export type OperatorIntent = "camera" | "risk" | "evidence" | "track" | "analytics" | "system" | "answer";
export type OperatorTarget = "cameras" | "events" | "risk" | "tracking" | "evidence" | "semantic" | "analytics" | "incidents" | "system";

export type OperatorRuntimeInput = {
  voiceState: VoiceState;
  voiceSessionState?: AegisVoiceSessionState;
  microphoneActive: boolean;
  commandPending: boolean;
  toolPending: boolean;
  execution: OperatorExecution | null;
  activeDomain: string | null;
  warning: boolean;
  error: string | null;
  listeningLevel: number;
  speakingLevel: number;
  target?: OperatorTarget | null;
};

export type OperatorRuntime = {
  state: OperatorState;
  activeGesture: OperatorGesture;
  intent: OperatorIntent;
  projectionAnchor: ProjectionAnchorName;
  attentionTarget: "operator" | "left" | "right" | "forward";
  listeningLevel: number;
  speakingLevel: number;
  target: OperatorTarget | null;
};

function bounded(level: number) {
  return Math.min(1, Math.max(0, Number.isFinite(level) ? level : 0));
}

export function operatorIntent(execution: OperatorExecution | null, activeDomain: string | null, target?: OperatorTarget | null): OperatorIntent {
  if (target === "cameras") return "camera";
  if (target === "events" || target === "risk" || target === "incidents") return "risk";
  if (target === "evidence" || target === "semantic") return "evidence";
  if (target === "tracking") return "track";
  if (target === "analytics") return "analytics";
  if (target === "system") return "system";
  const panel = execution?.panel ?? activeDomain;
  if (panel === "camera" || panel === "cameras") return "camera";
  if (panel === "events" || panel === "risk") return "risk";
  if (panel === "evidence" || panel === "semantic_results") return "evidence";
  if (panel === "tracks" || panel === "track") return "track";
  if (panel === "analytics") return "analytics";
  if (panel === "system") return "system";
  return "answer";
}

/** State priority mirrors real media/request lifecycles, not visual preference. */
export function operatorState(input: OperatorRuntimeInput): OperatorState {
  if (input.error || input.voiceState === "error" || input.execution?.error) return "ERROR";
  // PCM playback starts this state from NativePcmPlayer.onStarted, and stops it
  // from its actual drain callback. A non-zero amplitude is not required for a
  // quiet phoneme, so the native speaking event is the source of truth.
  if (input.voiceState === "speaking") return "SPEAKING";
  if (input.toolPending || input.commandPending) return "EXECUTING";
  if (input.voiceSessionState === "WAKE_DETECTED") return "LISTENING";
  if (input.voiceSessionState === "ACTIVATING") return "THINKING";
  if (input.voiceState === "thinking" || input.voiceState === "connecting") return "THINKING";
  // `microphoneActive` prevents an idle voice session from showing an invented
  // listening animation.
  if (input.voiceState === "listening" && input.microphoneActive) return "LISTENING";
  if (input.execution) return "PRESENTING";
  if (input.warning) return "WARNING";
  return "IDLE";
}

export function gestureFor(state: OperatorState, intent: OperatorIntent): OperatorGesture {
  if (state === "IDLE") return "idle";
  if (state === "LISTENING") return "listen";
  if (state === "THINKING") return "think";
  if (state === "SPEAKING") return "speak-neutral";
  if (state === "WARNING" || state === "ERROR") return "warning-attention";
  if (state === "EXECUTING") {
    if (intent === "camera") return "summon-right";
    if (intent === "risk") return "summon-left";
    if (intent === "evidence") return "point-right";
    if (intent === "track") return "point-left";
    return "push-forward";
  }
  if (intent === "camera") return "present-right";
  if (intent === "risk") return "present-left";
  if (intent === "evidence") return "point-right";
  if (intent === "track") return "point-left";
  return "push-forward";
}

export function projectionAnchorFor(intent: OperatorIntent): ProjectionAnchorName {
  if (intent === "camera" || intent === "evidence") return "rightHandProjectionAnchor";
  if (intent === "risk" || intent === "track") return "leftHandProjectionAnchor";
  if (intent === "analytics") return "rightSideProjectionAnchor";
  if (intent === "system") return "leftSideProjectionAnchor";
  return "centerProjectionAnchor";
}

export function attentionFor(state: OperatorState, intent: OperatorIntent): OperatorRuntime["attentionTarget"] {
  if (state === "LISTENING") return "operator";
  if (intent === "camera" || intent === "risk") return "left";
  if (intent === "evidence" || intent === "track" || intent === "analytics") return "right";
  return "forward";
}

/**
 * OperatorController's reducer-free snapshot. It keeps all animation inputs
 * together so a component never guesses state from a CSS timer.
 */
export function createOperatorRuntime(input: OperatorRuntimeInput): OperatorRuntime {
  const intent = operatorIntent(input.execution, input.activeDomain, input.target);
  const state = operatorState(input);
  return {
    state,
    activeGesture: gestureFor(state, intent),
    intent,
    projectionAnchor: projectionAnchorFor(intent),
    attentionTarget: attentionFor(state, intent),
    listeningLevel: state === "LISTENING" ? bounded(input.listeningLevel) : 0,
    speakingLevel: state === "SPEAKING" ? bounded(input.speakingLevel) : 0,
    target: input.target ?? null,
  };
}

export function stateLabelKey(state: OperatorState) {
  return state.toLowerCase() as Lowercase<OperatorState>;
}
