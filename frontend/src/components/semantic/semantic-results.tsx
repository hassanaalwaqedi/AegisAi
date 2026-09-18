"use client";

import Link from "next/link";
import { useState } from "react";
import { Camera, CheckCircle2, Database, ExternalLink, Eye, FileSearch, ShieldCheck, Sparkles, Tags, Video, WifiOff } from "lucide-react";

import { RiskBadge } from "@/components/dashboard/risk-badge";
import { Badge } from "@/components/ui/badge";
import { appConfig } from "@/lib/config";
import { formatDecimal, formatPercent, formatTimestamp } from "@/lib/data-format";
import { cn } from "@/lib/utils";
import type { Camera as CameraType, SemanticResultsResponse } from "@/types";

export type SemanticFilters = {
  cameraId: string;
  risk: "all" | "low" | "medium" | "high" | "critical";
  timeRange: "all" | "hour" | "day" | "week";
};

type SemanticResult = SemanticResultsResponse["results"][number];

type SemanticResultsProps = {
  data: SemanticResultsResponse;
  results: SemanticResult[];
  selectedId: string | null;
  onSelect: (result: SemanticResult) => void;
};

export function filterSemanticResults(results: SemanticResult[], filters: SemanticFilters) {
  return results.filter((result) => {
    if (filters.cameraId !== "all" && result.camera_id !== filters.cameraId) return false;
    if (filters.risk !== "all" && riskLevel(result.risk_score).toLowerCase() !== filters.risk) return false;
    if (filters.timeRange === "all") return true;
    if (!result.timestamp) return false;
    const time = Date.parse(result.timestamp);
    if (!Number.isFinite(time)) return false;
    const windowMs = filters.timeRange === "hour" ? 3_600_000 : filters.timeRange === "day" ? 86_400_000 : 604_800_000;
    return time >= Date.now() - windowMs;
  });
}

export function SemanticResults({ data, results, selectedId, onSelect }: SemanticResultsProps) {
  const selected = results.find((result) => String(result.track_id) === selectedId) ?? null;

  if (data.mode === "disabled" || data.evidence_storage === "unavailable") {
    return <SemanticUnavailableState reason={data.reason} />;
  }

  if (!data.results.length) {
    return <SemanticEmptyState query={data.query} />;
  }

  return (
    <section className="overflow-hidden rounded-xl border border-white/[0.1] bg-white/[0.025]" aria-labelledby="semantic-results-title">
      <div className="border-b border-white/[0.08] px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-signal-cyan">Results summary</p>
            <h2 id="semantic-results-title" className="mt-1 text-xl font-semibold tracking-tight text-white">Verified evidence matches</h2>
            <p className="mt-1 text-sm text-slate-400">{data.query ? `Results for “${data.query}”` : "Saved evidence matching your search"}</p>
          </div>
          <Badge variant="success"><ShieldCheck className="me-1 h-3.5 w-3.5" aria-hidden />Evidence-backed</Badge>
        </div>
        <div className="mt-5 grid gap-2 sm:grid-cols-2 2xl:grid-cols-4">
          <ResultMetric label="Matches" value={String(results.length)} detail={results.length === data.results.length ? "Current result set" : `${data.results.length} before filters`} />
          <ResultMetric label="Tracks evaluated" value={data.evaluated_tracks === undefined ? "Unavailable" : data.evaluated_tracks.toLocaleString()} detail="Search coverage" />
          <ResultMetric label="Events evaluated" value={data.evaluated_events === undefined ? "Unavailable" : data.evaluated_events.toLocaleString()} detail="Search coverage" />
          <ResultMetric label="Best confidence" value={selected ? formatPercent(selected.semantic_confidence) : "Unavailable"} detail={data.execution_ms === undefined ? "Search time unavailable" : `${formatDecimal(data.execution_ms, 1)} ms`} />
        </div>
      </div>

      {results.length ? <div className="divide-y divide-white/[0.08]">{results.map((result) => <EvidenceResultRow key={`${result.source ?? "track"}-${String(result.track_id)}`} result={result} selected={String(result.track_id) === selectedId} onSelect={onSelect} />)}</div> : <FilteredEmptyState />}
    </section>
  );
}

export function SemanticEvidencePreview({ result, cameras }: { result: SemanticResult | null; cameras: CameraType[] }) {
  const camera = cameras.find((item) => item.camera_id === result?.camera_id) ?? null;

  return (
    <section id="semantic-evidence-preview" tabIndex={-1} className="glass-panel overflow-hidden rounded-xl p-0 focus:outline-none focus:ring-2 focus:ring-signal-cyan" aria-labelledby="semantic-preview-title">
      <div className="flex items-center justify-between gap-3 px-5 py-4 sm:px-6">
        <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Evidence preview</p><h2 id="semantic-preview-title" className="mt-1 text-lg font-semibold text-white">{result?.camera_id ?? "No result selected"}</h2></div>
        {result ? <Badge variant="outline">{result.source ?? "track"}</Badge> : null}
      </div>
      <SemanticCameraPreview key={`${result?.camera_id ?? "none"}-${result ? String(result.track_id) : "none"}`} result={result} camera={camera} />
      {result ? <div className="grid grid-cols-2 gap-px border-y border-white/[0.08] bg-white/[0.08] sm:grid-cols-4"><PreviewFact label="Camera" value={camera?.name ?? result.camera_id ?? "Unavailable"} /><PreviewFact label="Time" value={result.timestamp ? formatTimestamp(result.timestamp) : "Unavailable"} /><PreviewFact label="Object" value={result.base_class} /><PreviewFact label="Risk" value={riskLevel(result.risk_score)} /></div> : null}
      {result?.camera_id ? <Link href={`/cameras?camera=${encodeURIComponent(result.camera_id)}&view=focus`} className="mx-5 my-4 flex min-h-10 items-center justify-center gap-2 rounded-md border border-white/10 text-sm font-medium text-slate-200 transition hover:border-signal-cyan/50 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan sm:mx-6"><Video className="h-4 w-4" aria-hidden />Open camera<ExternalLink className="h-3.5 w-3.5" aria-hidden /></Link> : null}
    </section>
  );
}

export function SemanticResultExplanation({ result, data }: { result: SemanticResult | null; data: SemanticResultsResponse }) {
  if (data.mode === "disabled" || data.evidence_storage === "unavailable") return null;

  return (
    <section className="rounded-xl border border-white/[0.1] bg-white/[0.025] p-5 sm:p-6" aria-labelledby="semantic-explanation-title">
      <div className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-signal-cyan" aria-hidden /><h2 id="semantic-explanation-title" className="text-lg font-semibold text-white">Why this result?</h2></div>
      {!result ? <p className="mt-3 text-sm text-slate-400">Select a result to review the saved evidence.</p> : <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <ExplanationItem icon={Tags} label="Matched tags" value={semanticTags(result).join(" · ") || "Unavailable"} />
        <ExplanationItem icon={FileSearch} label={result.source === "event" ? "Event reference" : "Track reference"} value={String(result.track_id)} />
        <ExplanationItem icon={Camera} label="Camera" value={result.camera_id ?? result.zone ?? "Unavailable"} />
        <ExplanationItem icon={ShieldCheck} label="Confidence" value={formatPercent(result.semantic_confidence)} />
        <ExplanationItem icon={Database} label="Evidence availability" value={data.evidence_storage === "available" ? "Available" : "Unavailable"} />
        <ExplanationItem icon={Eye} label="Snapshot status" value={result.camera_id ? "Preview available when selected" : "Unavailable"} />
      </div>}
    </section>
  );
}

function EvidenceResultRow({ result, selected, onSelect }: { result: SemanticResult; selected: boolean; onSelect: (result: SemanticResult) => void }) {
  const level = riskLevel(result.risk_score);
  const summary = result.evidence?.[0] ?? result.semantic_label ?? result.matched_phrase ?? "No additional evidence summary returned.";
  const cameraHref = result.camera_id ? `/cameras?camera=${encodeURIComponent(result.camera_id)}&view=focus` : null;

  return <article className={cn("grid gap-4 px-5 py-4 transition sm:px-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(200px,0.8fr)_auto] lg:items-center", selected && "bg-signal-cyan/[0.055]")}>
    <div className="min-w-0">
      <div className="flex items-start gap-3"><span className={cn("mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border", selected ? "border-signal-cyan/60 bg-signal-cyan/[0.12] text-signal-cyan" : "border-white/[0.12] bg-black/20 text-slate-300")}><Camera className="h-4.5 w-4.5" aria-hidden /></span><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="font-mono text-sm font-medium text-signal-cyan">{String(result.track_id)}</span><Badge variant={result.source === "event" ? "warning" : result.source === "statistics" ? "outline" : "default"}>{result.source ?? "track"}</Badge><RiskBadge level={level} /></div><p className="mt-1.5 text-sm font-medium text-white">{result.base_class}</p><p className="mt-1 line-clamp-2 text-sm leading-5 text-slate-400">{summary}</p></div></div>
    </div>
    <div className="grid grid-cols-2 gap-3 text-sm lg:block"><div><p className="text-xs uppercase tracking-[0.13em] text-slate-500">Confidence</p><div className="mt-1 flex items-center gap-2"><div className="h-1.5 min-w-14 flex-1 overflow-hidden rounded-full bg-white/[0.1]"><div className="h-full rounded-full bg-signal-cyan" style={{ width: `${clampPercent(result.semantic_confidence)}%` }} /></div><span className="text-slate-200">{formatPercent(result.semantic_confidence)}</span></div></div><div className="mt-3 lg:mt-4"><p className="text-xs uppercase tracking-[0.13em] text-slate-500">Camera / time</p><p className="mt-1 truncate text-slate-200">{result.camera_id ?? result.zone ?? "Unavailable"}</p><p className="mt-1 text-xs text-slate-500">{result.timestamp ? formatTimestamp(result.timestamp) : "Time unavailable"}</p></div></div>
    <div className="flex flex-wrap gap-2 lg:justify-end"><button type="button" onClick={() => { onSelect(result); document.getElementById("semantic-evidence-preview")?.scrollIntoView({ behavior: "smooth", block: "center" }); }} className="inline-flex min-h-9 items-center gap-2 rounded-md border border-signal-cyan/35 px-3 text-sm font-medium text-signal-cyan transition hover:bg-signal-cyan/[0.09] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><Eye className="h-4 w-4" aria-hidden />Review evidence</button>{cameraHref ? <Link href={cameraHref} className="inline-flex min-h-9 items-center gap-2 rounded-md border border-white/[0.12] px-3 text-sm font-medium text-slate-200 transition hover:border-signal-cyan/45 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><Video className="h-4 w-4" aria-hidden />Open camera</Link> : null}</div>
  </article>;
}

function SemanticCameraPreview({ result, camera }: { result: SemanticResult | null; camera: CameraType | null }) {
  const [failed, setFailed] = useState(false);
  const canRequestPreview = Boolean(result?.camera_id && camera?.runtime.status === "online" && camera.runtime.running);

  if (!result) return <div className="flex aspect-video items-center justify-center bg-black/30 px-6 text-center"><Database className="h-7 w-7 text-slate-600" aria-hidden /><p className="ms-3 text-sm text-slate-400">Run a search to review saved evidence.</p></div>;
  if (!canRequestPreview || failed) return <div className="flex aspect-video flex-col items-center justify-center bg-black/35 px-6 text-center"><WifiOff className="h-7 w-7 text-slate-500" aria-hidden /><p className="mt-3 text-sm font-medium text-slate-300">Preview unavailable</p><p className="mt-1 text-xs text-slate-500">{camera ? "The camera is not currently returning a live image." : "No matching live camera source was returned."}</p></div>;

  return <div className="relative aspect-video overflow-hidden bg-black">
    {/* eslint-disable-next-line @next/next/no-img-element -- authenticated camera snapshot comes from the internal proxy. */}
    <img src={`${appConfig.apiUrl}/cameras/${encodeURIComponent(result.camera_id!)}/snapshot?semantic=${encodeURIComponent(String(result.track_id))}`} alt={`Latest image from ${camera?.name ?? result.camera_id}`} className="h-full w-full object-cover" onError={() => setFailed(true)} />
    <span className="absolute start-3 top-3 rounded-md border border-emerald-300/35 bg-command-950/85 px-2 py-1 text-xs font-semibold text-emerald-200"><span className="me-1.5 inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden />Live camera</span>
  </div>;
}

function ResultMetric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="rounded-lg border border-white/[0.08] bg-black/[0.16] px-3 py-3"><p className="text-xs text-slate-500">{label}</p><p className="mt-1 truncate text-lg font-semibold text-white">{value}</p><p className="mt-0.5 truncate text-xs text-slate-500">{detail}</p></div>;
}

function PreviewFact({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0 bg-command-900/60 px-3 py-3"><p className="text-xs text-slate-500">{label}</p><p className="mt-1 truncate text-sm font-medium text-slate-200" title={value}>{value}</p></div>;
}

function ExplanationItem({ icon: Icon, label, value }: { icon: typeof Tags; label: string; value: string }) {
  return <div className="min-w-0 rounded-lg border border-white/[0.08] bg-black/[0.14] p-3"><div className="flex items-center gap-2 text-xs text-slate-500"><Icon className="h-3.5 w-3.5 text-signal-cyan" aria-hidden />{label}</div><p className="mt-2 break-words text-sm font-medium text-slate-200">{value}</p></div>;
}

function SemanticEmptyState({ query }: { query?: string | null }) {
  return <section className="flex min-h-80 flex-col items-center justify-center px-6 text-center"><Database className="h-8 w-8 text-slate-600" aria-hidden /><h2 className="mt-4 text-lg font-semibold text-white">{query ? "No evidence matched this search." : "Search saved security evidence."}</h2><p className="mt-2 max-w-md text-sm leading-6 text-slate-400">{query ? "Try a different camera, time range, or risk level." : "Enter a search to review saved evidence."}</p></section>;
}

function FilteredEmptyState() {
  return <section className="flex min-h-60 flex-col items-center justify-center px-6 text-center"><CheckCircle2 className="h-7 w-7 text-slate-600" aria-hidden /><h3 className="mt-3 text-base font-semibold text-white">No evidence matches the active filters.</h3><p className="mt-2 text-sm text-slate-400">Adjust the camera, time range, or risk level.</p></section>;
}

function SemanticUnavailableState({ reason: _reason }: { reason?: string | null }) {
  return <section className="flex min-h-80 flex-col items-center justify-center border border-eose-400/25 bg-rose-500/[0.06] px-6 text-center"><WifiOff className="h-8 w-8 text-rose-300" aria-hidden /><h2 className="mt-4 text-lg font-semibold text-rose-100">Evidence search is currently unavailable.</h2><p className="mt-2 max-w-lg text-sm leading-6 text-rose-100/75">Saved evidence cannot be searched right now. Try again shortly.</p></section>;
}

function riskLevel(score: number) {
  if (score >= 0.75) return "CRITICAL";
  if (score >= 0.5) return "HIGH";
  if (score >= 0.25) return "MEDIUM";
  return "LOW";
}

function clampPercent(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, Math.min(100, value * 100)) : 0;
}

function semanticTags(result: SemanticResult) {
  return [result.base_class, result.semantic_label, ...result.behaviors].filter((item): item is string => Boolean(item && item.trim()));
}
