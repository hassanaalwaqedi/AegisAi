"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  fetchIntelligenceContext,
  isContextStale,
  type IntelligenceContext,
  type IntelligenceContextError
} from "@/lib/intelligence-context";

export type IntelligenceContextPhase = "loading" | "ready" | "error";

export interface IntelligenceContextState {
  phase: IntelligenceContextPhase;
  context: IntelligenceContext | null;
  error: IntelligenceContextError | Error | null;
  isStale: boolean;
  refreshedAt: Date | null;
  refresh: () => Promise<void>;
}

/**
 * A bounded REST refresh is the Phase 0 fallback while authenticated event
 * delivery is not available. The interval comes from the backend contract
 * once it has loaded.
 */
export function useIntelligenceContext(): IntelligenceContextState {
  const [context, setContext] = useState<IntelligenceContext | null>(null);
  const [phase, setPhase] = useState<IntelligenceContextPhase>("loading");
  const [error, setError] = useState<IntelligenceContextError | Error | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);
  const [clock, setClock] = useState(() => Date.now());
  const mountedRef = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const nextContext = await fetchIntelligenceContext();
      if (!mountedRef.current) return;
      setContext(nextContext);
      setError(null);
      setPhase("ready");
      setRefreshedAt(new Date());
      setClock(Date.now());
    } catch (nextError) {
      if (!mountedRef.current) return;
      setError(nextError instanceof Error ? nextError : new Error("The intelligence context request failed."));
      setPhase("error");
      setClock(Date.now());
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void refresh();

    return () => {
      mountedRef.current = false;
    };
  }, [refresh]);

  const refreshAfterSeconds = context?.refreshAfterSeconds ?? 15;

  useEffect(() => {
    const interval = window.setInterval(() => {
      void refresh();
    }, Math.max(5, refreshAfterSeconds) * 1000);

    return () => window.clearInterval(interval);
  }, [refresh, refreshAfterSeconds]);

  useEffect(() => {
    const interval = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  return useMemo(
    () => ({
      phase,
      context,
      error,
      isStale: context ? isContextStale(context, clock) : false,
      refreshedAt,
      refresh
    }),
    [clock, context, error, phase, refresh, refreshedAt]
  );
}
