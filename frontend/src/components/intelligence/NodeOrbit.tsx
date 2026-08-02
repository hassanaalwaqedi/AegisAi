"use client";

import { motion, useReducedMotion } from "framer-motion";
import * as Icons from "lucide-react";

import { availabilityLabel } from "@/lib/intelligence-context";
import type { AgentNode } from "@/types/intelligence";
import type { VoiceCapabilityNodeId } from "./voice-core";

interface NodeOrbitProps {
  nodes: AgentNode[];
  activeNodeId?: VoiceCapabilityNodeId | null;
}

const DECORATIVE_FLOWS = [
  "M 0 18 C 17 20, 25 35, 40 43", "M 0 25 C 20 25, 26 38, 39 45",
  "M 0 32 C 16 34, 27 40, 40 47", "M 0 40 C 18 40, 29 44, 40 48",
  "M 0 48 C 18 48, 29 47, 40 49", "M 0 56 C 18 55, 29 50, 40 50",
  "M 0 64 C 17 62, 27 54, 40 51", "M 0 72 C 19 68, 29 57, 41 52",
  "M 0 80 C 20 73, 29 60, 42 53", "M 0 88 C 22 80, 31 64, 43 54",
  "M 100 16 C 83 18, 75 33, 60 43", "M 100 23 C 82 25, 74 38, 60 45",
  "M 100 30 C 82 31, 73 41, 60 47", "M 100 38 C 82 39, 72 45, 60 49",
  "M 100 46 C 82 46, 72 48, 60 50", "M 100 54 C 82 53, 72 51, 60 51",
  "M 100 62 C 81 60, 72 54, 60 52", "M 100 70 C 82 66, 71 57, 59 53",
  "M 100 78 C 81 72, 70 60, 59 54", "M 100 86 C 80 78, 69 64, 58 55",
  "M 12 10 C 34 9, 38 23, 48 39", "M 88 11 C 67 10, 62 24, 53 39",
  "M 14 91 C 33 88, 39 73, 47 58", "M 86 91 C 68 87, 61 73, 54 58",
];

function getIcon(name: string, size = 16) {
  const IconComponent = (Icons as Record<string, any>)[name];
  return IconComponent ? <IconComponent size={size} strokeWidth={1.65} /> : <Icons.Circle size={size} />;
}

function nodeTone(node: AgentNode) {
  if (node.availability === "live") return node.color;
  if (node.availability === "stale" || node.availability === "degraded") return "#f6c453";
  if (node.availability === "offline") return "#ff4f64";
  return "#62758d";
}

function connectorPath(node: AgentNode) {
  const direction = node.x < 50 ? -1 : 1;
  const coreEdge = 50 + direction * 12;
  const elbow = node.x - direction * 5;
  return `M ${coreEdge} 50 L ${elbow} 50 L ${elbow} ${node.y} L ${node.x} ${node.y}`;
}

/** Visual topology only. Node state and destinations still come from IntelligenceContext. */
export default function NodeOrbit({ nodes, activeNodeId = null }: NodeOrbitProps) {
  const reducedMotion = useReducedMotion();

  return (
    <div className="aegis-topology absolute inset-0" role="group" aria-label="Aegis capability network">
      <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <filter id="aegis-line-glow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="0.22" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <g className="aegis-network-flow" filter="url(#aegis-line-glow)">
          {DECORATIVE_FLOWS.map((d) => <path key={d} d={d} />)}
        </g>
        {nodes.map((node) => {
          const highlighted = activeNodeId === node.id;
          const tone = nodeTone(node);
          return (
            <g key={`line-${node.id}`} data-mobile-hidden={node.mobileHidden ? "true" : "false"}>
              <motion.path
                d={connectorPath(node)}
                fill="none"
                stroke={highlighted ? tone : "rgba(56,214,255,0.48)"}
                strokeWidth={highlighted ? 1.15 : 0.72}
                vectorEffect="non-scaling-stroke"
                filter={highlighted ? "url(#aegis-line-glow)" : undefined}
                strokeDasharray={highlighted ? "1.2 0.85" : undefined}
                animate={reducedMotion || !highlighted ? undefined : { strokeDashoffset: [0, -5] }}
                transition={{ duration: 1.8, repeat: Infinity, ease: "linear" }}
              />
              <circle cx={node.x} cy={node.y} r="0.5" fill={highlighted ? tone : "rgba(56,214,255,0.78)"} />
            </g>
          );
        })}
      </svg>

      {nodes.map((node) => {
        const highlighted = activeNodeId === node.id;
        const tone = nodeTone(node);
        const availability = node.availability === "planned"
          ? "Planned"
          : availabilityLabel(node.availability);
        const nodeContent = (
          <>
            <span className="aegis-node-icon" style={{ color: tone }}>{getIcon(node.icon)}</span>
            <span className={`aegis-node-copy ${node.labelSide === "left" ? "aegis-node-copy-left" : "aegis-node-copy-right"}`}>
              <span className="aegis-node-label">{node.label}</span>
              <span className="aegis-node-sublabel">{node.sublabel}</span>
              <span className="aegis-node-state">{availability}</span>
            </span>
          </>
        );
        const common = {
          left: `${node.x}%`, top: `${node.y}%`, "--node-tone": tone,
        } as React.CSSProperties;
        const classes = `aegis-capability-node ${highlighted ? "is-active" : ""}`;

        return node.href ? (
          <motion.a
            key={node.id}
            href={node.href}
            className={classes}
            style={common}
            data-mobile-hidden={node.mobileHidden ? "true" : "false"}
            whileHover={reducedMotion ? undefined : { scale: 1.08 }}
            whileTap={{ scale: 0.97 }}
            title={node.reason ?? `Open ${node.label}`}
            aria-label={`${node.label}: ${availability}. Open page.`}
          >{nodeContent}</motion.a>
        ) : (
          <div
            key={node.id}
            className={`${classes} is-static`}
            style={common}
            data-mobile-hidden={node.mobileHidden ? "true" : "false"}
            title={node.reason ?? `${node.label} is ${availability.toLowerCase()}.`}
          >{nodeContent}<span className="sr-only">{node.reason ?? `${node.label} is ${availability.toLowerCase()}; no action is available.`}</span></div>
        );
      })}
    </div>
  );
}
