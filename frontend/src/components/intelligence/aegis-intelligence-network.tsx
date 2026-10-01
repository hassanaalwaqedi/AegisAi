"use client";

import { useMemo } from "react";
import {
  Activity,
  BarChart3,
  Camera,
  Database,
  ScanSearch,
  ServerCog,
  ShieldAlert,
  Siren,
  Waypoints,
} from "lucide-react";

import type { OperatorRuntime, OperatorTarget } from "@/lib/operator-runtime";

export type AegisNetworkNodeId = OperatorTarget;

type NetworkNode = {
  id: AegisNetworkNodeId;
  label: string;
  subtitle: string;
  command: string;
  x: number;
  y: number;
  side: "left" | "right" | "bottom";
  Icon: typeof Camera;
};

const NODES: NetworkNode[] = [
  { id: "cameras",   label: "Cameras",   subtitle: "Live Monitoring",               command: "Open camera",                      x: 10, y: 18, side: "left",   Icon: Camera },
  { id: "events",    label: "Events",    subtitle: "Real-time Events",              command: "Show recent events",               x: 10, y: 40, side: "left",   Icon: Activity },
  { id: "risk",      label: "Risk",      subtitle: "Risk Assessment",               command: "Show high-risk events",            x: 10, y: 62, side: "left",   Icon: ShieldAlert },
  { id: "system",    label: "System",    subtitle: "Core Intelligence",             command: "Show system status",               x: 38, y: 84, side: "bottom", Icon: ServerCog },
  { id: "incidents", label: "Incidents", subtitle: "Investigation & Case Management", command: "Show high-risk events",           x: 62, y: 84, side: "bottom", Icon: Siren },
  { id: "evidence",  label: "Evidence",  subtitle: "Digital Evidence",              command: "Find recent evidence",             x: 90, y: 18, side: "right",  Icon: Database },
  { id: "semantic",  label: "Semantic",  subtitle: "AI Understanding",              command: "Search evidence for recent activity", x: 90, y: 36, side: "right", Icon: ScanSearch },
  { id: "analytics", label: "Analytics", subtitle: "Insights & Reports",            command: "Show analytics",                   x: 90, y: 54, side: "right",  Icon: BarChart3 },
  { id: "tracking",  label: "Tracking",  subtitle: "People & Assets",              command: "Show active tracks",               x: 90, y: 72, side: "right",  Icon: Waypoints },
];

type NetworkState = "BOOTING" | "READY" | "LISTENING" | "THINKING" | "EXECUTING" | "PRESENTING" | "SPEAKING" | "ALERT";

function networkState(runtime: OperatorRuntime): NetworkState {
  if (runtime.state === "WARNING" || runtime.state === "ERROR") return "ALERT";
  if (runtime.state === "LISTENING") return "LISTENING";
  if (runtime.state === "THINKING") return "THINKING";
  if (runtime.state === "EXECUTING") return "EXECUTING";
  if (runtime.state === "PRESENTING") return "PRESENTING";
  if (runtime.state === "SPEAKING") return "SPEAKING";
  return "READY";
}

function nodeForRuntime(runtime: OperatorRuntime, activeDomain: string | null, requestedNode: AegisNetworkNodeId | null): AegisNetworkNodeId | null {
  if (requestedNode) return requestedNode;
  if (runtime.intent === "camera") return "cameras";
  if (runtime.intent === "risk") return "risk";
  if (runtime.intent === "evidence") return activeDomain === "semantic_results" ? "semantic" : "evidence";
  if (runtime.intent === "track") return "tracking";
  if (runtime.intent === "analytics") return "analytics";
  if (runtime.intent === "system") return "system";
  if (activeDomain === "events") return "events";
  return null;
}

/** Generate an elegant SVG curve from node to the core center */
function connector(node: NetworkNode) {
  const coreX = 50;
  const coreY = 48;
  if (node.side === "left") {
    const startX = node.x + 7;
    const cpx1 = startX + 12;
    const cpx2 = coreX - 14;
    return `M ${startX} ${node.y} C ${cpx1} ${node.y}, ${cpx2} ${coreY}, ${coreX - 8} ${coreY}`;
  }
  if (node.side === "right") {
    const startX = node.x - 7;
    const cpx1 = startX - 12;
    const cpx2 = coreX + 14;
    return `M ${startX} ${node.y} C ${cpx1} ${node.y}, ${cpx2} ${coreY}, ${coreX + 8} ${coreY}`;
  }
  // bottom
  const startY = node.y - 5;
  const cpy1 = startY - 10;
  const cpy2 = coreY + 12;
  return `M ${node.x} ${startY} C ${node.x} ${cpy1}, ${coreX} ${cpy2}, ${coreX} ${coreY + 6}`;
}

export type AegisNetworkMetrics = Partial<Record<AegisNetworkNodeId, string>>;
export type AegisNetworkStatuses = Partial<Record<AegisNetworkNodeId, string>>;
export type AegisNetworkSignals = Partial<Record<AegisNetworkNodeId, number[]>>;

const BOOT_LABELS = ["SYSTEM CHECK", "CORE AWAKENING", "NETWORK INIT", "NETWORK EXPANSION", "MODULES LINKING", "FULL NETWORK", "READY"];

export function AegisIntelligenceNetwork({
  runtime,
  activeDomain,
  metrics,
  statuses,
  signals,
  cameraPreviewUrl,
  bootStep,
  requestedNode = null,
  onCommand,
}: {
  runtime: OperatorRuntime;
  activeDomain: string | null;
  metrics: AegisNetworkMetrics;
  statuses: AegisNetworkStatuses;
  signals: AegisNetworkSignals;
  cameraPreviewUrl?: string | null;
  bootStep: number;
  requestedNode?: AegisNetworkNodeId | null;
  onCommand: (command: string, node: AegisNetworkNodeId) => void;
}) {
  const state = bootStep < 6 ? "BOOTING" : networkState(runtime);
  const focusedNode = nodeForRuntime(runtime, activeDomain, requestedNode);

  const activeNodes = useMemo(() => {
    if (state === "BOOTING") return new Set<AegisNetworkNodeId>();
    if (state === "ALERT") return new Set<AegisNetworkNodeId>(["risk", "incidents"]);
    if (["THINKING", "EXECUTING", "PRESENTING", "SPEAKING"].includes(state) && focusedNode) return new Set<AegisNetworkNodeId>([focusedNode]);
    return new Set<AegisNetworkNodeId>();
  }, [focusedNode, state]);

  return (
    <section className="aegis-intelligence-network" data-boot-step={bootStep} data-network-state={state} aria-label="Aegis intelligence network">
      {bootStep < 6 ? <div className="aegis-network-boot" role="status" aria-live="polite">
        <span>{BOOT_LABELS[Math.min(bootStep, BOOT_LABELS.length - 1)]}</span>
        <i aria-hidden />
        <small>{bootStep + 1} / 7</small>
      </div> : null}

      {/* SVG connection paths */}
      <svg className="aegis-network-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <radialGradient id="aegis-core-gradient">
            <stop stopColor="#d8fbff" />
            <stop offset=".24" stopColor="#55dcff" />
            <stop offset=".72" stopColor="#087fab" stopOpacity=".42" />
            <stop offset="1" stopColor="#02121f" stopOpacity="0" />
          </radialGradient>
          <filter id="aegis-network-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation=".45" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Concentric rings around core */}
        <g className="aegis-network-rings">
          <circle cx="50" cy="48" r="8" />
          <circle cx="50" cy="48" r="14" />
          <circle cx="50" cy="48" r="22" />
          <circle cx="50" cy="48" r="31" />
        </g>

        {/* Core glow */}
        <circle className="aegis-network-core-glow" cx="50" cy="48" r="11" fill="url(#aegis-core-gradient)" />

        {/* Connection traces */}
        <g className="aegis-network-traces" filter="url(#aegis-network-glow)">
          {NODES.map((node) => (
            <path key={node.id} className={activeNodes.has(node.id) ? "is-active" : ""} d={connector(node)} />
          ))}
        </g>

        {/* Ambient particles near core */}
        <g className="aegis-network-particles">
          <circle cx="45" cy="42" r=".34" />
          <circle cx="55" cy="43" r=".25" />
          <circle cx="52" cy="55" r=".38" />
          <circle cx="47" cy="54" r=".22" />
          <circle cx="58" cy="49" r=".28" />
        </g>
      </svg>

      {/* Module node cards */}
      {NODES.map((node, index) => {
        const active = activeNodes.has(node.id);
        const Icon = node.Icon;
        const signal = signals[node.id] ?? [];
        return (
          <button
            key={node.id}
            type="button"
            className="aegis-network-node"
            data-node={node.id}
            data-side={node.side}
            data-active={active}
            data-status={statuses[node.id] ?? "unavailable"}
            style={
              {
                "--node-x": `${node.x}%`,
                "--node-y": `${node.y}%`,
                "--node-order": index,
              } as React.CSSProperties
            }
            onClick={() => onCommand(node.command, node.id)}
            aria-label={`${node.label}. ${metrics[node.id] ?? "Data unavailable"}. Activate ${node.label}.`}
          >
            <span className="aegis-network-node-header">
              <span className="aegis-network-node-pin"><Icon aria-hidden /></span>
              <span className="aegis-network-node-copy">
                <strong>{node.label}</strong>
                <small>{node.subtitle}</small>
              </span>
              <i className="aegis-network-node-status" aria-hidden />
            </span>
            {node.id === "cameras" && cameraPreviewUrl ? (
              <span className="aegis-network-node-preview">
                {/* eslint-disable-next-line @next/next/no-img-element -- live authenticated Aegis camera snapshot. */}
                <img src={cameraPreviewUrl} alt="" />
                <b>LIVE</b>
              </span>
            ) : signal.length ? (
              <span className="aegis-network-node-signal" aria-hidden>
                {signal.slice(0, 12).map((value, signalIndex) => (
                  <i key={signalIndex} style={{ "--signal-value": Math.max(.08, Math.min(1, value)) } as React.CSSProperties} />
                ))}
              </span>
            ) : (
              <span className="aegis-network-node-metric">
                {metrics[node.id] ?? "—"}
              </span>
            )}
          </button>
        );
      })}
    </section>
  );
}
