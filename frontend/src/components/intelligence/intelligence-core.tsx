"use client";

import dynamic from "next/dynamic";

import type { Availability } from "@/lib/intelligence-context";
import type { OperatorAssetStatus, OperatorRuntime, ProjectionAnchor, ProjectionAnchorName } from "@/lib/operator-runtime";

const CinematicOperatorCanvas = dynamic(
  () => import("./cinematic-operator-canvas").then((module) => module.CinematicOperatorCanvas),
  { ssr: false, loading: () => <div className="operator-runtime-loading">Loading Aegis operator runtime…</div> },
);

type IntelligenceCoreProps = {
  runtime: OperatorRuntime;
  status: Availability;
  statusLabel: string;
  stateLabel: string;
  onAnchors: (anchors: Record<ProjectionAnchorName, ProjectionAnchor>) => void;
  onAssetStatus?: (status: OperatorAssetStatus) => void;
};

/**
 * Visual shell around the rigged-GLB runtime. It intentionally contains no
 * image layer and no CSS transform that pretends to animate a character.
 */
export function IntelligenceCore({ runtime, status, statusLabel, stateLabel, onAnchors, onAssetStatus }: IntelligenceCoreProps) {
  const voiceLevel = runtime.state === "SPEAKING" ? runtime.speakingLevel : runtime.listeningLevel;
  return (
    <div
      className="cinematic-core"
      data-operator-state={runtime.state}
      data-gesture={runtime.activeGesture}
      data-intent={runtime.intent}
      data-status={status}
      data-presence={runtime.state.toLowerCase()}
      data-domain={runtime.intent}
      style={{ "--voice-level": voiceLevel } as React.CSSProperties}
    >
      <div className="cinematic-core-aura" aria-hidden />
      <div className="cinematic-orbit cinematic-orbit-outer" aria-hidden />
      <div className="cinematic-orbit cinematic-orbit-inner" aria-hidden />
      <div className="cinematic-scan-plane" aria-hidden />
      <div className="cinematic-data-streams" aria-hidden>{Array.from({ length: 12 }, (_, index) => <i key={index} />)}</div>
      <CinematicOperatorCanvas runtime={runtime} onAnchors={onAnchors} onAssetStatus={onAssetStatus} />
      <div className="cinematic-voice-ring" aria-hidden>
        {Array.from({ length: 24 }, (_, index) => <i key={index} style={{ "--bar": index } as React.CSSProperties} />)}
      </div>
      <div className="cinematic-identity" data-contextual={runtime.state !== "IDLE"} aria-live="polite">
        {runtime.state !== "IDLE" ? <strong>{stateLabel}</strong> : <i data-status={status} aria-hidden />}
        {runtime.state === "WARNING" || runtime.state === "ERROR" ? <small>{statusLabel}</small> : null}
      </div>
    </div>
  );
}
