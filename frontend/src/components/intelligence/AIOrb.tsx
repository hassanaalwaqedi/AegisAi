"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Mic, Square } from "lucide-react";

import { availabilityLabel, type Availability } from "@/lib/intelligence-context";
import type { AudibleRiskVisualState } from "@/hooks/useAudibleRiskAlerts";
import type { AegisVoiceCoreState, VoiceCapabilityNodeId } from "./voice-core";
import { voiceCoreStateLabel } from "./voice-core";

interface AIOrbProps {
  contextStatus: Availability;
  voiceState: AegisVoiceCoreState;
  microphoneLevel: number;
  playbackLevel: number;
  activeCapability?: VoiceCapabilityNodeId | null;
  onActivate: () => void;
  onListenToggle: () => void;
  listeningEnabled: boolean;
  voiceSessionActive: boolean;
  audibleRiskState?: AudibleRiskVisualState;
}

function useReducedMotion() {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return reducedMotion;
}

function voiceColors(voiceState: AegisVoiceCoreState, contextStatus: Availability) {
  if (voiceState === "error") return { glow: "rgba(56,214,255,0.34)", ring: "#38d6ff", dot: "#f6c453" };
  if (voiceState === "degraded" || contextStatus === "degraded" || contextStatus === "stale") {
    return { glow: "rgba(56,214,255,0.34)", ring: "#38d6ff", dot: "#f6c453" };
  }
  if (contextStatus === "offline" || contextStatus === "unavailable") {
    return { glow: "rgba(56,214,255,0.22)", ring: "#38d6ff", dot: "#94a3b8" };
  }
  return { glow: "rgba(20,190,255,0.38)", ring: "#38d6ff", dot: "#2dd4bf" };
}

/** The visible intelligence core. Audio-reactive movement uses analyser data only. */
export default function AIOrb({
  contextStatus,
  voiceState,
  microphoneLevel,
  playbackLevel,
  activeCapability,
  onActivate,
  onListenToggle,
  listeningEnabled,
  voiceSessionActive,
  audibleRiskState = "unavailable",
}: AIOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reducedMotion = useReducedMotion();
  const colors = voiceColors(voiceState, contextStatus);
  const realLevel = voiceState === "listening" ? microphoneLevel : voiceState === "speaking" ? playbackLevel : 0;
  const measuredScale = 1 + Math.min(0.2, Math.max(0, realLevel) * 0.2);
  const hasMeasuredLevel = realLevel > 0.015;
  const stateLabel = voiceCoreStateLabel(voiceState);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const size = 320;
    const pixelRatio = window.devicePixelRatio || 1;
    canvas.width = size * pixelRatio;
    canvas.height = size * pixelRatio;
    context.scale(pixelRatio, pixelRatio);
    const particles = Array.from({ length: 52 }, (_, index) => ({
      angle: (index / 52) * Math.PI * 2,
      distance: 58 + ((index * 29) % 92),
      radius: 0.45 + ((index * 7) % 8) / 10,
      alpha: 0.16 + ((index * 13) % 45) / 100,
    }));
    let animationFrame = 0;
    let tick = 0;
    const draw = () => {
      tick += 0.006;
      context.clearRect(0, 0, size, size);
      for (const particle of particles) {
        const angle = particle.angle + (reducedMotion ? 0 : tick);
        context.beginPath();
        context.arc(160 + Math.cos(angle) * particle.distance, 160 + Math.sin(angle) * particle.distance, particle.radius, 0, Math.PI * 2);
        context.fillStyle = `rgba(56, 214, 255, ${particle.alpha})`;
        context.fill();
      }
      if (!reducedMotion) animationFrame = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(animationFrame);
  }, [reducedMotion]);

  const statusDescription = voiceState === "off"
    ? "Ready. The microphone is off until Ask Aegis is clicked."
    : `${stateLabel}. Intelligence context is ${availabilityLabel(contextStatus).toLowerCase()}.`;

  return (
    <div
      className="aegis-core"
      data-testid="aegis-voice-orb"
      data-voice-state={voiceState}
      data-active-capability={activeCapability ?? ""}
      data-audible-risk={audibleRiskState}
      data-reduced-motion={reducedMotion ? "true" : "false"}
      style={{ "--core-tone": colors.ring, "--core-glow": colors.glow } as React.CSSProperties}
    >
      <canvas ref={canvasRef} className="aegis-core-particles" width={320} height={320} aria-hidden="true" />
      <motion.div
        className="aegis-core-aura"
        animate={reducedMotion ? undefined : { scale: hasMeasuredLevel ? measuredScale : [1, 1.035, 1], opacity: [0.58, 0.92, 0.58] }}
        transition={{ duration: hasMeasuredLevel ? 0.12 : 3.8, repeat: Infinity, ease: "easeInOut" }}
        aria-hidden="true"
      />
      <div className="aegis-core-orbit aegis-core-orbit-outer" aria-hidden="true" />
      <div className="aegis-core-orbit aegis-core-orbit-inner" aria-hidden="true" />
      <motion.div
        className="aegis-core-sphere"
        animate={reducedMotion ? undefined : { scale: hasMeasuredLevel ? measuredScale : voiceState === "thinking" ? [1, 1.025, 1] : 1 }}
        transition={{ duration: hasMeasuredLevel ? 0.12 : 1.5, repeat: voiceState === "thinking" ? Infinity : 0, ease: "easeInOut" }}
        aria-hidden="true"
      >
        <svg className="aegis-core-mesh" viewBox="0 0 100 100" aria-hidden="true">
          <path d="M8 49 L26 30 L49 48 L68 20 L91 44 M12 67 L35 57 L51 74 L76 61 L92 79 M25 11 L42 35 L61 14 L76 38 M18 84 L40 66 L63 88 L87 57" />
          <path d="M49 8 L49 92 M8 50 L92 50 M24 22 L77 78 M78 22 L22 78" />
          <circle cx="26" cy="30" r="1.3" /><circle cx="49" cy="48" r="1.6" /><circle cx="68" cy="20" r="1.3" /><circle cx="35" cy="57" r="1.2" /><circle cx="76" cy="61" r="1.3" /><circle cx="63" cy="88" r="1" />
        </svg>
        <span className="aegis-core-grid aegis-core-grid-latitude" />
        <span className="aegis-core-grid aegis-core-grid-longitude" />
        <span className="aegis-core-grid aegis-core-grid-diagonal" />
        <span className="aegis-core-star" />
      </motion.div>

      <button
        type="button"
        onClick={onActivate}
        className="aegis-core-button"
        aria-label={`Aegis Voice Core. ${statusDescription}`}
        aria-describedby="aegis-voice-core-status"
      >
        <span className="aegis-core-wordmark">AEGIS</span>
        <span className="aegis-core-caption">Intelligence core</span>
        <span className="aegis-core-state" style={{ color: colors.dot }}>
          <span style={{ backgroundColor: colors.dot }} />{stateLabel}
        </span>
        {activeCapability && <span className="aegis-core-active">{activeCapability}</span>}
      </button>

      <button
        type="button"
        onClick={onListenToggle}
        disabled={!listeningEnabled}
        className="aegis-core-action"
        aria-label={voiceSessionActive ? "Stop listening" : "Ask Aegis"}
        title={voiceSessionActive ? "Stop listening and release the microphone" : "Microphone access begins only after this click."}
      >
        {voiceSessionActive ? <Square size={12} /> : <Mic size={13} />}
        {voiceSessionActive ? "Stop listening" : "Voice"}
      </button>

      <span id="aegis-voice-core-status" className="sr-only" aria-live="polite">{statusDescription}</span>
    </div>
  );
}
