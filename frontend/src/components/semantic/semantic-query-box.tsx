"use client";

import { ChevronDown, Clock3, Filter, Search, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useSemanticQueryMutation } from "@/hooks/use-aegis-api";
import type { Camera } from "@/types";
import type { SemanticFilters } from "@/components/semantic/semantic-results";

const promptExamples = [
  "High-risk events",
  "Person near restricted zone",
  "Weapon-like object",
  "Crowd movement",
  "Recent evidence",
  "Camera offline",
];

type SemanticQueryBoxProps = {
  cameras: Camera[];
  camerasUnavailable: boolean;
  filters: SemanticFilters;
  onFiltersChange: (filters: SemanticFilters) => void;
};

export function SemanticQueryBox({ cameras, camerasUnavailable, filters, onFiltersChange }: SemanticQueryBoxProps) {
  const t = useTranslations("semantic");
  const [prompt, setPrompt] = useState("");
  const mutation = useSemanticQueryMutation();

  const updateFilter = <Key extends keyof SemanticFilters>(key: Key, value: SemanticFilters[Key]) => {
    onFiltersChange({ ...filters, [key]: value });
  };

  const submit = (value = prompt) => {
    const nextPrompt = value.trim();
    if (nextPrompt.length < 3) return;
    setPrompt(nextPrompt);
    mutation.mutate(nextPrompt);
  };

  return (
    <section className="glass-panel rounded-xl p-5 sm:p-6" aria-labelledby="semantic-command-title">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-signal-cyan">{t("askAegis")}</p>
          <h2 id="semantic-command-title" className="mt-1 text-xl font-semibold tracking-tight text-white">{t("searchVerified")}</h2>
        </div>
        <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-signal-cyan/25 bg-signal-cyan/[0.07] text-signal-cyan"><Search className="h-4 w-4" aria-hidden /></span>
      </div>

      <form className="mt-5" onSubmit={(event) => { event.preventDefault(); submit(); }}>
        <label className="sr-only" htmlFor="semantic-evidence-search">{t("label")}</label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden />
            <Input id="semantic-evidence-search" value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder={t("searchPlaceholder")} className="min-h-12 ps-10" />
          </div>
          <Button type="submit" disabled={mutation.isPending || prompt.trim().length < 3} className="min-h-12 shrink-0 px-5"><Search className="h-4 w-4" aria-hidden />{mutation.isPending ? t("searchingBtn") : t("searchBtn")}</Button>
        </div>
      </form>

      <div className="mt-4">
        <p className="text-xs font-medium text-slate-400">{t("quickQueries")}</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {promptExamples.map((example) => (
            <button key={example} type="button" onClick={() => submit(example)} disabled={mutation.isPending} className="min-h-9 rounded-md border border-white/[0.1] bg-white/[0.035] px-3 text-xs font-medium text-slate-200 transition hover:border-signal-cyan/45 hover:bg-signal-cyan/[0.07] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan disabled:cursor-not-allowed disabled:opacity-60">
              {example}
            </button>
          ))}
        </div>
      </div>

      <details className="mt-5 border-t border-white/[0.08] pt-4">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><span className="inline-flex items-center gap-2"><SlidersHorizontal className="h-4 w-4 text-signal-cyan" aria-hidden />{t("filters")}</span><ChevronDown className="h-4 w-4 text-slate-400" aria-hidden /></summary>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <label className="block"><span className="mb-1.5 flex items-center gap-1.5 text-xs text-slate-400"><Clock3 className="h-3.5 w-3.5" aria-hidden />{t("timeRange")}</span><Select value={filters.timeRange} onChange={(event) => updateFilter("timeRange", event.target.value as SemanticFilters["timeRange"])}><option value="all">{t("allTime")}</option><option value="hour">{t("lastHour")}</option><option value="day">{t("last24h")}</option><option value="week">{t("last7d")}</option></Select></label>
          <label className="block"><span className="mb-1.5 text-xs text-slate-400">{t("camera")}</span><Select value={filters.cameraId} onChange={(event) => updateFilter("cameraId", event.target.value)} disabled={camerasUnavailable}><option value="all">{t("allCameras")}</option>{cameras.map((camera) => <option key={camera.camera_id} value={camera.camera_id}>{camera.name ?? camera.camera_id}</option>)}</Select>{camerasUnavailable ? <span className="mt-1 block text-xs text-amber-100">{t("cameraListUnavailable")}</span> : null}</label>
          <label className="block"><span className="mb-1.5 flex items-center gap-1.5 text-xs text-slate-400"><Filter className="h-3.5 w-3.5" aria-hidden />{t("riskLevel")}</span><Select value={filters.risk} onChange={(event) => updateFilter("risk", event.target.value as SemanticFilters["risk"])}><option value="all">{t("allRiskLevels")}</option><option value="low">{t("low")}</option><option value="medium">{t("medium")}</option><option value="high">{t("high")}</option><option value="critical">{t("critical")}</option></Select></label>
        </div>
      </details>

      {mutation.isSuccess ? <div className="mt-4 flex items-center gap-2 rounded-lg border border-emerald-300/20 bg-emerald-400/[0.055] px-3 py-2 text-sm text-emerald-100"><span className="h-2 w-2 rounded-full bg-emerald-400" aria-hidden />{typeof mutation.data.matches === "number" ? `${mutation.data.matches} ${mutation.data.matches === 1 ? t("matchFound") : t("matchesFound")}` : t("searchSubmitted")}</div> : null}
      {mutation.isError ? <div className="mt-4 rounded-lg border border-rose-400/25 bg-rose-500/[0.06] px-3 py-2 text-sm text-rose-100">{t("unavailableReason")}</div> : null}
    </section>
  );
}
