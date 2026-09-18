"use client";

import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { LoaderCircle, Maximize2, Minimize2, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { OperatorResultWorkspace } from "./operator-result-workspace";
import type { OperatorExecution } from "@/lib/operator-api";

export function ProjectionLayer({ execution, pending, domain, selectedId, onSelect, onDismiss, onOpen, onFindSimilar, onRelated }: {
  execution: OperatorExecution | null; pending: boolean; domain: string | null; selectedId: string | null;
  onSelect: (id: string) => void; onDismiss: () => void; onOpen: (target: string) => void;
  onFindSimilar: (id: string) => void; onRelated: () => void;
}) {
  const t = useTranslations("intelligence.operator");
  const reduced = useReducedMotion();
  const [expanded, setExpanded] = useState(false);
  const side = domain === "cameras" || domain === "events" ? "left" : "right";
  return <AnimatePresence>
    {(execution || pending) && <motion.aside
      key="projection" className="cinematic-result-projection" data-side={side} data-expanded={expanded} data-domain={domain}
      aria-label={t("resultWorkspace")} aria-busy={pending}
      initial={reduced ? false : { opacity: 0, scale: .85, x: side === "left" ? 70 : -70, y: 35 }}
      animate={{ opacity: 1, scale: 1, x: 0, y: 0 }} exit={{ opacity: 0, scale: .95 }}
      transition={{ duration: reduced ? 0 : .45 }}
    >
      <div className="projection-hand-link" aria-hidden><i /><span /></div>
      <div className="projection-controls">
        <button type="button" aria-label={expanded ? "Collapse projection" : "Expand projection"} aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? <Minimize2 /> : <Maximize2 />}</button>
        <button type="button" onClick={onDismiss} aria-label={t("closeResult")}><X /></button>
      </div>
      {pending && <div className="projection-progress" role="status"><LoaderCircle className="animate-spin" aria-hidden />{t("executing")}</div>}
      {execution && <OperatorResultWorkspace execution={execution} selectedId={selectedId} onSelect={onSelect} onRelated={onRelated} onOpen={onOpen} onFindSimilar={onFindSimilar} />}
    </motion.aside>}
  </AnimatePresence>;
}
