"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Activity, AlertCircle, AlertTriangle, Info, Shield } from "lucide-react";

import { availabilityLabel, formatFreshness } from "@/lib/intelligence-context";
import type { IntelligenceFeedItem } from "@/types/intelligence";

const severityConfig = {
  critical: { color: "#ff4f64", background: "rgba(255,79,100,0.1)", border: "rgba(255,79,100,0.2)", icon: AlertTriangle },
  high: { color: "#ff4f64", background: "rgba(255,79,100,0.08)", border: "rgba(255,79,100,0.15)", icon: AlertCircle },
  medium: { color: "#f6c453", background: "rgba(246,196,83,0.08)", border: "rgba(246,196,83,0.15)", icon: Shield },
  low: { color: "#2dd4bf", background: "rgba(45,212,191,0.08)", border: "rgba(45,212,191,0.15)", icon: Activity },
  info: { color: "#38d6ff", background: "rgba(56,214,255,0.06)", border: "rgba(56,214,255,0.12)", icon: Info }
};

interface ActivityFeedProps {
  items: IntelligenceFeedItem[];
  emptyMessage: string;
}

export default function ActivityFeed({ items, emptyMessage }: ActivityFeedProps) {
  if (items.length === 0) {
    return (
      <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-white/10 px-4 text-center" role="status">
        <p className="text-[11px] leading-relaxed text-white/35">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="custom-scrollbar flex max-h-[280px] flex-col gap-1.5 overflow-y-auto pe-1" aria-label="Recent evidence">
      <AnimatePresence initial={false}>
        {items.slice(0, 8).map((item) => {
          const config = severityConfig[item.severity];
          const Icon = config.icon;

          return (
            <motion.div
              key={item.id}
              initial={{ opacity: 0, x: 20, height: 0 }}
              animate={{ opacity: 1, x: 0, height: "auto" }}
              exit={{ opacity: 0, x: -20, height: 0 }}
              transition={{ duration: 0.3 }}
              className="flex items-start gap-2.5 rounded-lg p-2.5"
              style={{ background: config.background, border: `1px solid ${config.border}` }}
            >
              <div className="mt-0.5 shrink-0 rounded-md p-1" style={{ background: `${config.color}15` }}>
                <Icon size={12} style={{ color: config.color }} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[11px] font-semibold text-white/90">{item.title}</span>
                  <span
                    className="shrink-0 rounded-full px-1.5 py-0.5 text-[8px] font-medium"
                    style={{ background: `${config.color}15`, color: config.color }}
                  >
                    {item.severity === "info" ? "Info" : item.severity.charAt(0).toUpperCase() + item.severity.slice(1)}
                  </span>
                </div>
                <p className="mt-0.5 truncate text-[10px] text-white/45">{item.description}</p>
                <span className="mt-0.5 block text-[9px] text-white/25">
                  {item.source} · {item.availability === "unavailable"
                    ? "Timestamp unavailable"
                    : `${availabilityLabel(item.availability)} · ${formatFreshness(item.observedAt)}`}
                </span>
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
