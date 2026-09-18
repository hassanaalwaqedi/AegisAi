"use client";

import Image from "next/image";
import { motion, useReducedMotion } from "framer-motion";

import type { Availability } from "@/lib/intelligence-context";

import type { OperatorPresenceState } from "@/lib/operator-scene";
export type { OperatorPresenceState } from "@/lib/operator-scene";

type IntelligenceCoreProps = {
  presence: OperatorPresenceState;
  activeDomain?: string | null;
  status: Availability;
  statusLabel: string;
  stateLabel: string;
  voiceLevel?: number;
};

const domainDirection = (domain?: string | null) => {
  if (domain === "cameras" || domain === "events") return -1;
  if (domain === "evidence" || domain === "tracks" || domain === "analytics" || domain === "system") return 1;
  return 0;
};

export function IntelligenceCore({
  presence,
  activeDomain,
  status,
  statusLabel,
  stateLabel,
  voiceLevel = 0,
}: IntelligenceCoreProps) {
  const reducedMotion = useReducedMotion();
  const direction = domainDirection(activeDomain);
  const responsiveLevel = Math.min(1, Math.max(0, voiceLevel));
  const operatorAnimation = reducedMotion
    ? undefined
    : presence === "executing" || presence === "presenting"
      ? { x: direction * 22, rotateY: direction * 7, scale: 1.025, y: -4 }
      : presence === "listening"
        ? { x: 0, rotateY: 0, scale: 1.025 + responsiveLevel * 0.015, y: -5 }
        : presence === "thinking"
          ? { x: [0, -3, 2, 0], rotateY: [0, -2, 2, 0], scale: 1.015 }
          : presence === "speaking"
            ? { scale: 1.01 + responsiveLevel * 0.025, y: -responsiveLevel * 4, rotateZ: responsiveLevel * .5 }
            : presence === "warning" ? { y: -2, scale: 1.01 } : { y: [0, -6, 0], rotateZ: [-.25, .25, -.25], scale: [1, 1.012, 1] };

  return (
    <div
      className="cinematic-core"
      data-presence={presence}
      data-domain={activeDomain || "none"}
      data-status={status}
      style={{ "--voice-level": responsiveLevel } as React.CSSProperties}
    >
      <div className="cinematic-core-aura" aria-hidden />
      <motion.div
        className="cinematic-orbit cinematic-orbit-outer"
        animate={reducedMotion ? undefined : { rotate: 360 }}
        transition={{ duration: presence === "thinking" || presence === "executing" ? 12 : 34, repeat: Infinity, ease: "linear" }}
        aria-hidden
      />
      <motion.div
        className="cinematic-orbit cinematic-orbit-inner"
        animate={reducedMotion ? undefined : { rotate: -360 }}
        transition={{ duration: presence === "thinking" || presence === "executing" ? 8 : 24, repeat: Infinity, ease: "linear" }}
        aria-hidden
      />
      <div className="cinematic-scan-plane" aria-hidden />
      <div className="cinematic-data-streams" aria-hidden>{Array.from({ length: 12 }, (_, index) => <i key={index} />)}</div>
      <motion.div
        className="cinematic-operator-figure"
        animate={operatorAnimation}
        transition={presence === "idle" ? { duration: 4.6, repeat: Infinity, ease: "easeInOut" } : presence === "thinking" ? { duration: 1.8, repeat: Infinity, ease: "easeInOut" } : { duration: presence === "speaking" ? .12 : .6, ease: "easeOut" }}
      >
        <Image
          className="operator-body-layer"
          src="/images/aegis-holographic-operator.png"
          alt="Aegis holographic AI operator"
          fill
          priority
          sizes="(max-width: 720px) 92vw, 580px"
        />
        <motion.div className="operator-head-layer" aria-hidden
          animate={reducedMotion ? undefined : presence === "presenting" || presence === "executing" ? { rotateZ: direction * 1.8, x: direction * 2, y: -1 } : presence === "speaking" ? { rotateZ: responsiveLevel * 1.4, y: -responsiveLevel * 2 } : presence === "listening" ? { rotateZ: 0, y: -2, x: 0 } : { rotateZ: [-.35, .35, -.35], y: [0, -1, 0], x: 0 }}
          transition={presence === "idle" ? { duration: 6, repeat: Infinity, ease: "easeInOut" } : { duration: .25 }}>
          <Image src="/images/aegis-holographic-operator.png" alt="" fill sizes="(max-width: 720px) 92vw, 580px" />
        </motion.div>
        <div className="cinematic-operator-scan" aria-hidden />
        <div className="cinematic-focus-halo" aria-hidden />
        <div className="operator-hand-anchor" data-direction={direction} aria-hidden><i /><span /></div>
      </motion.div>
      <div className="cinematic-gesture-trail" aria-hidden><span /></div>
      <div className="cinematic-voice-ring" aria-hidden>
        {Array.from({ length: 24 }, (_, index) => <i key={index} style={{ "--bar": index } as React.CSSProperties} />)}
      </div>
      <div className="cinematic-identity">
        <span>AEGIS / OPERATOR</span>
        <strong>{stateLabel}</strong>
        <small><i data-status={status} />{statusLabel}</small>
      </div>
    </div>
  );
}
