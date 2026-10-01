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
    incident: "risk",
    recording: "cameras",
    statistics: "analytics",
    health: null,
  };
  return nodeByKind[citation.kind];
}

export function nodeForSafeUiCommand(command: SafeUICommand): VoiceCapabilityNodeId | null {
  const nodeByCommand: Record<SafeUICommand["kind"], VoiceCapabilityNodeId | null> = {
    open_workspace: null,
    close_operator_view: null,
    open_cameras: "cameras",
    open_incident: "risk",
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
    get_recent_incidents: "risk",
    get_incident: "risk",
    get_incident_evidence: "risk",
    get_incident_timeline: "risk",
    generate_incident_report: "risk",
    analyze_incident_with_vlm: "risk",
    get_track_trajectory: "tracking",
    search_live_evidence: "semantic",
    get_pipeline_health: "analytics",
    get_gpu_usage: "analytics",
    get_intelligence_context: null,
    get_agent_permissions: null,
    navigate_workspace: null,
    close_operator_view: null,
    control_camera_runtime: "cameras",
    open_authorised_evidence: null,
  };
  return nodeByTool[tool] ?? null;
}

export function routeForCitation(citation: LiveCitation) {
  if (citation.kind === "incident") {
    const incidentId = citation.evidenceId.startsWith("incident:") ? citation.evidenceId.slice("incident:".length) : "";
    return incidentId ? `/events?incident=${encodeURIComponent(incidentId)}` : "/events";
  }
  if (citation.kind === "camera") {
    return citation.cameraId ? `/cameras?camera=${encodeURIComponent(citation.cameraId)}&view=focus` : "/cameras";
  }
  if (citation.kind === "event") {
    const eventId = citation.evidenceId.startsWith("event:") ? citation.evidenceId.slice("event:".length) : "";
    return eventId ? `/events?event=${encodeURIComponent(eventId)}` : "/events";
  }
  if (citation.kind === "track") {
    const trackId = citation.evidenceId.startsWith("track:") ? citation.evidenceId.slice("track:".length) : "";
    const params = new URLSearchParams();
    if (trackId) params.set("track", trackId);
    if (citation.cameraId) params.set("camera", citation.cameraId);
    return params.size ? `/tracks?${params.toString()}` : "/tracks";
  }
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
  if (command.kind === "open_incident") {
    if (!command.targetId) return;
    window.location.assign(`/events?incident=${encodeURIComponent(command.targetId)}`);
    return;
  }
  if (command.kind === "open_cameras") {
    const target = command.cameraId ? `/cameras?camera=${encodeURIComponent(command.cameraId)}&view=focus` : "/cameras";
    window.location.assign(target);
    return;
  }
  if (command.kind === "show_track_evidence") {
    const params = new URLSearchParams();
    if (command.targetId) params.set("track", command.targetId);
    if (command.cameraId) params.set("camera", command.cameraId);
    window.location.assign(params.size ? `/tracks?${params.toString()}` : "/tracks");
    return;
  }
  if (command.kind === "show_risk_evidence") {
    const target = command.targetId ? `/events?event=${encodeURIComponent(command.targetId)}` : "/events";
    window.location.assign(target);
    return;
  }
  window.location.assign("/semantic");
}
