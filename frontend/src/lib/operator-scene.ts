import type { OperatorExecution } from "./operator-api";
import type { VoiceState } from "./live-voice";

export type OperatorPresenceState = "idle" | "listening" | "thinking" | "speaking" | "executing" | "presenting" | "warning";
export type ProjectionRecord = Record<string, unknown>;

export function resultRecords(execution: OperatorExecution | null): ProjectionRecord[] {
  if (!execution) return [];
  const data = execution.result;
  const rows = data.events ?? data.evidence ?? data.tracks ?? data.cameras ?? (data.camera ? [data.camera] : []);
  return Array.isArray(rows) ? rows.filter((row): row is ProjectionRecord => !!row && typeof row === "object") : [];
}

export function recordId(row: ProjectionRecord): string {
  return String(row.event_id ?? row.id ?? row.track_id ?? row.camera_id ?? "");
}

export function projectionDomain(panel?: string) {
  return panel === "camera" ? "cameras" : panel ?? null;
}

export function operatorPresence({ voice, capturing, pending, toolPending, execution, warning }: {
  voice: VoiceState; capturing: boolean; pending: boolean; toolPending: boolean; execution: OperatorExecution | null; warning: boolean;
}): OperatorPresenceState {
  if (voice === "speaking") return "speaking";
  if (pending || toolPending) return "executing";
  if (voice === "thinking" || voice === "connecting") return "thinking";
  if (capturing && voice === "listening") return "listening";
  if (execution?.error || execution?.panel === "error") return "warning";
  if (execution) return "presenting";
  return warning ? "warning" : "idle";
}

export function wantsFullView(message: string) {
  return /\b(full (?:view|details|camera|evidence|timeline|page)|open (?:the )?page|deep investigation)\b|عرض كامل|التفاصيل الكاملة/i.test(message);
}

export function selectedOrdinal(message: string): number | null {
  if (!/\b(open|show|select|expand)\b|افتح|اعرض/i.test(message)) return null;
  const match = message.match(/\b(first|second|third|fourth|fifth|\d+(?:st|nd|rd|th)?)\s+(?:one|result|event|item)\b|\b(?:result|item|event)\s*#?\s*(\d+)\b/i);
  if (!match) return null;
  const token = (match[1] || match[2]).toLowerCase();
  const named = ["first", "second", "third", "fourth", "fifth"].indexOf(token);
  return named >= 0 ? named : parseInt(token, 10) - 1;
}
