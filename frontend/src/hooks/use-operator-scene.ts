"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { executeOperatorCommand, type OperatorExecution } from "@/lib/operator-api";
import { projectionDomain, recordId, resultRecords, selectedOrdinal, wantsFullView } from "@/lib/operator-scene";

function serializeContext(value: { execution: OperatorExecution | null; selectedId: string | null; query: string }) {
  return JSON.stringify({ panel: value.execution?.panel || "answer", query: value.query.slice(0, 500), selected_id: value.selectedId, ordered_ids: resultRecords(value.execution).map(recordId).slice(0, 50) });
}

export function useOperatorScene(openTarget: (target: string) => void) {
  const [execution, setExecution] = useState<OperatorExecution | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [domain, setDomain] = useState<string | null>(null);
  const [sceneContext, setSceneContext] = useState(() => serializeContext({ execution: null, selectedId: null, query: "" }));
  const context = useRef<{ execution: OperatorExecution | null; selectedId: string | null; query: string }>({ execution: null, selectedId: null, query: "" });
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  const select = useCallback((id: string) => {
    if (!resultRecords(context.current.execution).some((row) => recordId(row) === id)) return;
    context.current.selectedId = id;
    setSceneContext(serializeContext(context.current));
    setSelectedId(id);
  }, []);

  const run = useCallback(async (message: string, evidenceId?: string) => {
    if (message.trim().length < 2) return;
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setError(null);
    setPending(false);
    const previous = context.current;
    const ordinal = selectedOrdinal(message);
    if (ordinal !== null) {
      const item = resultRecords(previous.execution)[ordinal];
      if (!item) { setError("That result is not in the current projection. Select one of the displayed results."); return; }
      select(recordId(item));
      return;
    }
    if (wantsFullView(message) && previous.execution?.target && !/\bcamera\s+\d+/i.test(message)) {
      const target = previous.execution.target;
      const selected = previous.selectedId;
      openTarget(selected && previous.execution.panel === "events" ? `${target}${target.includes("?") ? "&" : "?"}event=${encodeURIComponent(selected)}` : target);
      return;
    }
    setPending(true);
    setDomain(/camera/i.test(message) ? "cameras" : /evidence|find|search/i.test(message) ? "evidence" : /risk|event/i.test(message) ? "events" : /track/i.test(message) ? "tracks" : projectionDomain(previous.execution?.panel));
    try {
      const result = await executeOperatorCommand(message, {
        previous_intent: previous.execution?.intent,
        previous_query: previous.query.slice(0, 500) || undefined,
        previous_evidence_id: evidenceId || (previous.execution?.panel === "events" || previous.execution?.panel === "evidence" ? previous.selectedId || undefined : undefined),
        selected_track_id: previous.execution?.panel === "tracks" ? previous.selectedId || undefined : undefined,
        selected_camera_id: previous.execution?.panel === "camera" ? String(previous.execution.result.camera && (previous.execution.result.camera as Record<string, unknown>).camera_id || "") || undefined : undefined,
      }, request.signal);
      if (request.signal.aborted) return;
      const firstId = resultRecords(result)[0];
      const id = firstId ? recordId(firstId) : null;
      context.current = { execution: result, selectedId: id, query: message };
      setSceneContext(serializeContext(context.current));
      setExecution(result);
      setSelectedId(id);
      setDomain(projectionDomain(result.panel));
      if (wantsFullView(message) && result.target && !result.error) openTarget(result.target);
    } catch (failure) {
      if (!request.signal.aborted) setError(failure instanceof Error ? failure.message : "The request could not be completed.");
    } finally {
      if (controller.current === request) setPending(false);
    }
  }, [openTarget, select]);

  const dismiss = useCallback(() => {
    controller.current?.abort();
    setPending(false);
    setExecution(null);
    setDomain(null);
    // Keep the ordered result context for the next follow-up, even after dismissal.
  }, []);
  const present = useCallback((result: OperatorExecution, message: string) => {
    controller.current?.abort();
    setPending(false);
    setError(null);
    const rows = resultRecords(result);
    const id = rows.length ? recordId(rows[0]) : null;
    context.current = { execution: result, selectedId: id, query: message };
    setSceneContext(serializeContext(context.current));
    setExecution(result);
    setSelectedId(id);
    setDomain(projectionDomain(result.panel));
    if (wantsFullView(message) && result.target && !result.error) openTarget(result.target);
  }, [openTarget]);
  return { execution, pending, error, selectedId, domain, run, select, dismiss, present, sceneContext };
}
