import type { Availability } from "@/lib/intelligence-context";

export interface AgentNode {
  id: string;
  label: string;
  sublabel: string;
  icon: string;
  /** Percentage coordinates inside the cinematic intelligence map. */
  x: number;
  y: number;
  color: string;
  availability: Availability | "planned";
  href?: string;
  reason?: string;
  labelSide?: "left" | "right";
  mobileHidden?: boolean;
}

export interface IntelligenceFeedItem {
  id: string;
  type: "alert" | "event" | "track";
  severity: "critical" | "high" | "medium" | "low" | "info";
  title: string;
  description: string;
  observedAt: string;
  source: string;
  availability: Availability;
}
