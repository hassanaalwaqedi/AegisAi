"use client";

import { useMemo } from "react";
import type { OperatorRuntime } from "@/lib/operator-runtime";
import type { Availability } from "@/lib/intelligence-context";

/**
 * Abstract Aegis Intelligence Core — the central non-human visualization.
 *
 * Renders a holographic neural sphere with geometric shield, orbital rings,
 * flowing data streams, particles, and the Aegis symbol. Built entirely with
 * SVG + CSS for 60 FPS performance without WebGL overhead.
 */
export function AegisCoreVisualization({
  runtime,
  status,
  statusLabel,
  stateLabel,
}: {
  runtime: OperatorRuntime;
  status: Availability;
  statusLabel: string;
  stateLabel: string;
}) {
  // Native playback can report very quiet phonemes as a zero-level sample.
  // Keep a small speaking floor so the core still responds to the real
  // SPEAKING state, while louder audio drives a larger pulse.
  const voiceLevel = runtime.state === "SPEAKING"
    ? Math.max(0.18, runtime.speakingLevel)
    : runtime.listeningLevel;
  const speakingScale = 1.045 + voiceLevel * 0.055;

  const particles = useMemo(
    () =>
      Array.from({ length: 28 }, (_, i) => ({
        id: i,
        cx: 50 + Math.cos((i / 28) * Math.PI * 2 + i * 0.3) * (18 + (i % 5) * 6),
        cy: 50 + Math.sin((i / 28) * Math.PI * 2 + i * 0.3) * (18 + (i % 4) * 5),
        r: 0.3 + (i % 3) * 0.2,
        delay: i * 0.25,
      })),
    [],
  );

  const streamLines = useMemo(
    () =>
      Array.from({ length: 16 }, (_, i) => ({
        id: i,
        angle: (i / 16) * 360,
        length: 14 + (i % 4) * 4,
        delay: i * 0.3,
      })),
    [],
  );

  return (
    <div
      className="aegis-core-viz"
      data-state={runtime.state}
      data-status={status}
      data-intent={runtime.intent}
      style={{ "--voice-level": voiceLevel, "--core-speaking-scale": speakingScale } as React.CSSProperties}
    >
      {/* Ambient aura */}
      <div className="aegis-core-viz-aura" aria-hidden />

      {/* Orbital rings */}
      <div className="aegis-core-viz-orbit aegis-core-viz-orbit--outer" aria-hidden />
      <div className="aegis-core-viz-orbit aegis-core-viz-orbit--mid" aria-hidden />
      <div className="aegis-core-viz-orbit aegis-core-viz-orbit--inner" aria-hidden />

      {/* Scan plane (floor grid) */}
      <div className="aegis-core-viz-scan" aria-hidden />

      {/* Data streams radiating from core */}
      <div className="aegis-core-viz-streams" aria-hidden>
        {streamLines.map((line) => (
          <i
            key={line.id}
            style={
              {
                "--stream-angle": `${line.angle}deg`,
                "--stream-length": `${line.length}%`,
                "--stream-delay": `${line.delay}s`,
              } as React.CSSProperties
            }
          />
        ))}
      </div>

      {/* SVG layer: neural sphere + shield + mesh + particles */}
      <svg
        className="aegis-core-viz-svg"
        viewBox="0 0 100 100"
        aria-hidden="true"
      >
        <defs>
          <radialGradient id="core-sphere-gradient" cx="48%" cy="42%">
            <stop offset="0%" stopColor="#d6fbff" stopOpacity="0.95" />
            <stop offset="22%" stopColor="#55dcff" stopOpacity="0.72" />
            <stop offset="52%" stopColor="#0a7baa" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#021420" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="core-inner-glow" cx="50%" cy="50%">
            <stop offset="0%" stopColor="#a0f0ff" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#0a3a5a" stopOpacity="0" />
          </radialGradient>
          <filter id="core-glow-filter" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="1.2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Neural mesh grid lines */}
        <g className="aegis-core-viz-mesh" opacity="0.35">
          {/* Latitude lines */}
          <ellipse cx="50" cy="50" rx="22" ry="6" fill="none" stroke="#5ee8ff" strokeWidth="0.25" strokeDasharray="1.5 1" />
          <ellipse cx="50" cy="50" rx="22" ry="12" fill="none" stroke="#5ee8ff" strokeWidth="0.2" strokeDasharray="1.2 1.5" />
          <ellipse cx="50" cy="50" rx="22" ry="18" fill="none" stroke="#5ee8ff" strokeWidth="0.2" strokeDasharray="1 1.8" />
          {/* Longitude lines */}
          <ellipse cx="50" cy="50" rx="6" ry="22" fill="none" stroke="#5ee8ff" strokeWidth="0.25" strokeDasharray="1.5 1" />
          <ellipse cx="50" cy="50" rx="12" ry="22" fill="none" stroke="#5ee8ff" strokeWidth="0.2" strokeDasharray="1.2 1.5" />
          <ellipse cx="50" cy="50" rx="18" ry="22" fill="none" stroke="#5ee8ff" strokeWidth="0.2" strokeDasharray="1 1.8" />
          {/* Diagonal */}
          <ellipse cx="50" cy="50" rx="16" ry="22" fill="none" stroke="#45d4ff" strokeWidth="0.15" strokeDasharray="0.8 2" transform="rotate(42, 50, 50)" />
        </g>

        {/* Core sphere */}
        <circle
          className="aegis-core-viz-sphere"
          cx="50"
          cy="50"
          r="22"
          fill="url(#core-sphere-gradient)"
          stroke="#61e8ff"
          strokeWidth="0.5"
          filter="url(#core-glow-filter)"
        />

        {/* Inner energy core */}
        <circle cx="50" cy="50" r="9" fill="url(#core-inner-glow)" />

        {/* Geometric shield — hexagonal */}
        <g className="aegis-core-viz-shield" filter="url(#core-glow-filter)">
          <polygon
            points="50,27 67,38.5 67,61.5 50,73 33,61.5 33,38.5"
            fill="none"
            stroke="#42d7ff"
            strokeWidth="0.5"
            strokeLinejoin="round"
            opacity="0.55"
          />
          <polygon
            points="50,31 63.5,40 63.5,60 50,69 36.5,60 36.5,40"
            fill="none"
            stroke="#38d6ff"
            strokeWidth="0.3"
            strokeLinejoin="round"
            strokeDasharray="2 1.5"
            opacity="0.35"
          />
        </g>

        {/* Aegis symbol — abstract shield / chevron mark */}
        <g className="aegis-core-viz-symbol" opacity="0.9">
          {/* Outer shield shape */}
          <path
            d="M50 38 L58 44 L58 54 L50 60 L42 54 L42 44 Z"
            fill="none"
            stroke="#a8f2ff"
            strokeWidth="0.6"
            strokeLinejoin="round"
          />
          {/* Inner chevron / "A" mark */}
          <path
            d="M50 42 L54 47 L54 53 L50 56 L46 53 L46 47 Z"
            fill="rgba(90, 230, 255, 0.15)"
            stroke="#cff8ff"
            strokeWidth="0.4"
            strokeLinejoin="round"
          />
          {/* Center dot — energy core */}
          <circle cx="50" cy="49" r="1.5" fill="#e8fdff" />
        </g>

        {/* Network node connection dots on sphere surface */}
        <g className="aegis-core-viz-nodes" filter="url(#core-glow-filter)">
          <circle cx="37" cy="38" r="0.7" fill="#8af2ff" />
          <circle cx="63" cy="38" r="0.7" fill="#8af2ff" />
          <circle cx="35" cy="55" r="0.6" fill="#6ae8ff" />
          <circle cx="65" cy="55" r="0.6" fill="#6ae8ff" />
          <circle cx="50" cy="30" r="0.8" fill="#a0f5ff" />
          <circle cx="50" cy="70" r="0.8" fill="#a0f5ff" />
          <circle cx="30" cy="48" r="0.5" fill="#5ee2ff" />
          <circle cx="70" cy="48" r="0.5" fill="#5ee2ff" />
        </g>

        {/* Floating particles */}
        <g className="aegis-core-viz-particles">
          {particles.map((p) => (
            <circle
              key={p.id}
              cx={p.cx}
              cy={p.cy}
              r={p.r}
              fill="#8af4ff"
              opacity="0.45"
              style={{ "--particle-delay": `${p.delay}s` } as React.CSSProperties}
            />
          ))}
        </g>
      </svg>

      {/* Voice activity ring */}
      <div className="aegis-core-viz-voice-ring" aria-hidden>
        {Array.from({ length: 32 }, (_, i) => (
          <i
            key={i}
            style={{
              "--bar-index": i,
              "--bar-delay": `${-((i % 7) * 0.06)}s`,
              "--bar-peak": Math.min(1, 0.38 + voiceLevel * (0.45 + (i % 5) * 0.07)),
            } as React.CSSProperties}
          />
        ))}
      </div>

      {/* Identity label */}
      <div className="aegis-core-viz-identity" aria-live="polite">
        <span>AEGIS</span>
        <strong>AI CORE INTELLIGENCE</strong>
        {runtime.state !== "IDLE" ? (
          <small data-state={runtime.state}>{stateLabel}</small>
        ) : (
          <small>
            <i className="aegis-core-viz-status-dot" data-status={status} />
            {statusLabel}
          </small>
        )}
      </div>
    </div>
  );
}
