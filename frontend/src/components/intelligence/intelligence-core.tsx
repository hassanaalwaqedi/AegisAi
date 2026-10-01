"use client";

import type { Availability } from "@/lib/intelligence-context";
import type { OperatorAssetStatus, OperatorRuntime, ProjectionAnchor, ProjectionAnchorName } from "@/lib/operator-runtime";
import { defaultProjectionAnchors } from "@/lib/operator-runtime";
import { AegisCoreVisualization } from "./aegis-core-visualization";
import { useEffect } from "react";

const DEFAULT_ANCHORS = defaultProjectionAnchors();

type IntelligenceCoreProps = {
  runtime: OperatorRuntime;
  status: Availability;
  statusLabel: string;
  stateLabel: string;
  onAnchors: (anchors: Record<ProjectionAnchorName, ProjectionAnchor>) => void;
  onAssetStatus?: (status: OperatorAssetStatus) => void;
};

/**
 * Visual shell around the abstract Aegis Intelligence Core.
 * Replaces the previous humanoid robot with a non-human central
 * intelligence visualization.
 */
export function IntelligenceCore({ runtime, status, statusLabel, stateLabel, onAnchors, onAssetStatus }: IntelligenceCoreProps) {
  // Provide default projection anchors (no rigging needed for abstract core)
  useEffect(() => {
    onAnchors(DEFAULT_ANCHORS);
  }, [onAnchors]);

  useEffect(() => {
    onAssetStatus?.("ready");
  }, [onAssetStatus]);

  return (
    <div
      className="cinematic-core"
      data-operator-state={runtime.state}
      data-gesture={runtime.activeGesture}
      data-intent={runtime.intent}
      data-status={status}
      data-presence={runtime.state.toLowerCase()}
      data-domain={runtime.intent}
    >
      <AegisCoreVisualization
        runtime={runtime}
        status={status}
        statusLabel={statusLabel}
        stateLabel={stateLabel}
      />
    </div>
  );
}
