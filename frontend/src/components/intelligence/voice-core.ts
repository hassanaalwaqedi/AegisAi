import type { AegisVoiceCoreState, LiveCitation, SafeUICommand } from "@/lib/live-voice";

export type { AegisVoiceCoreState } from "@/lib/live-voice";

export type VoiceCapabilityNodeId = "cameras" | "tracking" | "risk" | "semantic" | "analytics";

export function voiceCoreStateLabel(state: AegisVoiceCoreState) {
  const labels: Record<AegisVoiceCoreState, string> = {
    off: "Ready",
    connecting: "Connecting",
    ready: "Ready",
    listening: "Listening",
    thinking: "Analysing",
    speaking: "Aegis speaking",
    degraded: "Voice degraded",
    error: "Voice error",
  };
  return labels[state];
}

export function nodeForCitation(citation: LiveCitation): VoiceCapabilityNodeId | null {
  const nodeByKind: Record<LiveCitation["kind"], VoiceCapabilityNodeId | null> = {
    camera: "cameras",
    track: "tracking",
    detection: "tracking",
    alert: "risk",
    event: "risk",
    recording: "cameras",
    statistics: "analytics",
    health: null,
  };
  return nodeByKind[citation.kind];
}

export function nodeForSafeUiCommand(command: SafeUICommand): VoiceCapabilityNodeId | null {
  const nodeByCommand: Record<SafeUICommand["kind"], VoiceCapabilityNodeId | null> = {
    open_cameras: "cameras",
    show_track_evidence: "tracking",
    open_semantic_evidence: "semantic",
    show_risk_evidence: "risk",
    focus_health: null,
  };
  return nodeByCommand[command.kind];
}

/** Only allowlisted server tools may illuminate a corresponding live node. */
export function nodeForLiveTool(tool: string): VoiceCapabilityNodeId | null {
  const nodeByTool: Record<string, VoiceCapabilityNodeId | null> = {
    get_live_camera_status: "cameras",
    get_track_details: "tracking",
    get_active_risk_alerts: "risk",
    get_risk_explanation: "risk",
    get_recent_events: "risk",
    search_live_evidence: "semantic",
    get_pipeline_health: "analytics",
    get_intelligence_context: null,
    open_authorised_evidence: null,
  };
  return nodeByTool[tool] ?? null;
}

export function routeForCitation(citation: LiveCitation) {
  const node = nodeForCitation(citation);
  if (node === "cameras") return "/cameras";
  if (node === "tracking") return "/tracks";
  if (node === "risk") return "/events";
  if (node === "semantic") return "/semantic";
  if (node === "analytics") return "/analytics";
  return null;
}

export function applySafeUiCommand(command: SafeUICommand) {
  if (command.kind === "focus_health") {
    document.getElementById("intelligence-health-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }
  const node = nodeForSafeUiCommand(command);
  const route = node === "cameras"
    ? "/cameras"
    : node === "tracking"
      ? "/tracks"
      : node === "semantic"
        ? "/semantic"
        : "/events";
  window.location.assign(route);
}
