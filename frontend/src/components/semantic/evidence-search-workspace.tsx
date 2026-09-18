"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useRouter, useSearchParams } from "next/navigation";
import { Camera, ChevronLeft, ChevronRight, Database, ExternalLink, FileSearch, LoaderCircle, Search, ShieldAlert, SlidersHorizontal, Sparkles, Tag, WifiOff } from "lucide-react";
import { cn, formatTime } from "@/lib/utils";
import { appConfig } from "@/lib/config";
import { getErrorMessage } from "@/lib/errors";
import { useCamerasQuery, useEvidenceSearchDetailQuery, useEvidenceSearchQuery, useEvidenceSearchStatusQuery, useStatusQuery } from "@/hooks/use-aegis-api";
import type { EvidenceSearchRequest, EvidenceSearchResponse } from "@/types";

const quickQueryKeys = ["quickPerson", "quickWeapon", "quickRisk", "quickCrowd", "quickVehicle", "quickUnattended"] as const;
type Tab = "insights" | "metadata" | "related" | "entities";

function dateFromRange(value: string) {
  const hours = value === "hour" ? 1 : value === "day" ? 24 : value === "week" ? 168 : 0;
  return hours ? new Date(Date.now() - hours * 3_600_000).toISOString() : null;
}

function parseRequest(params: URLSearchParams): EvidenceSearchRequest {
  const raw = {
    query: params.get("q") ?? "", similar_to: params.get("similar") || null,
    camera_id: params.get("camera") || null, event_type: params.get("type") || null,
    risk_level: params.get("risk") || null, start: dateFromRange(params.get("time") ?? "all"),
    min_confidence: Number(params.get("confidence") ?? 0), sort: params.get("sort") ?? "relevance",
    page: Number(params.get("page") ?? 1), page_size: 6
  };
  const riskLevels = ["LOW", "CANDIDATE_MEDIUM", "MEDIUM", "HIGH", "CRITICAL"] as const;
  const sorts = ["relevance", "newest", "oldest", "risk", "confidence"] as const;
  return {
    query: raw.query, similar_to: raw.similar_to, camera_id: raw.camera_id, event_type: raw.event_type,
    risk_level: riskLevels.includes(raw.risk_level as typeof riskLevels[number]) ? raw.risk_level as typeof riskLevels[number] : null,
    start: raw.start, min_confidence: Number.isFinite(raw.min_confidence) ? Math.max(0, Math.min(1, raw.min_confidence)) : 0,
    sort: sorts.includes(raw.sort as typeof sorts[number]) ? raw.sort as typeof sorts[number] : "relevance",
    page: Number.isInteger(raw.page) && raw.page > 0 ? raw.page : 1, page_size: 6, min_similarity: 0.25
  };
}

export function EvidenceSearchWorkspace() {
  const t = useTranslations("semantic");
  const locale = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const request = useMemo(() => parseRequest(new URLSearchParams(searchParams.toString())), [searchParams]);
  const active = Boolean(request.query || request.similar_to);
  const [draft, setDraft] = useState(request.query);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("insights");
  const cameras = useCamerasQuery();
  const status = useStatusQuery();
  const index = useEvidenceSearchStatusQuery();
  const search = useEvidenceSearchQuery(request, active);
  const selected = search.data?.results.find((item) => item.event_id === selectedId) ?? search.data?.results[0] ?? null;
  const detail = useEvidenceSearchDetailQuery(selected?.event_id ?? null);
  const quickQueries = quickQueryKeys.map((key) => t(key));

  const setParams = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(changes)) value ? next.set(key, value) : next.delete(key);
    if (!Object.hasOwn(changes, "page")) next.delete("page");
    router.replace(`/${locale}/semantic${next.size ? `?${next.toString()}` : ""}`, { scroll: false });
  };
  const submit = (query = draft) => {
    const value = query.trim();
    if (value.length < 3) return;
    setDraft(value); setSelectedId(null); setTab("insights"); setParams({ q: value, similar: null });
  };
  const reset = () => { setDraft(""); setSelectedId(null); router.replace(`/${locale}/semantic`, { scroll: false }); };
  const online = cameras.data?.cameras.filter((camera) => camera.runtime.status === "online" && camera.runtime.running).length;

  return <section className="semantic-workspace mx-auto w-full max-w-[1800px] px-4 py-4 sm:px-6 lg:px-8" aria-labelledby="semantic-evidence-title">
    <header className="semantic-header">
      <div><p className="semantic-kicker">{t("label")}</p><h1 id="semantic-evidence-title">{t("title")}</h1><p>{t("subtitle")}</p></div>
      <SemanticStatus index={index.data} indexLoading={index.isLoading} online={online} total={cameras.data?.cameras.length} camerasLoading={cameras.isLoading} detectionRunning={status.data?.system?.running} />
    </header>
    {index.isError ? <ErrorNotice message={getErrorMessage(index.error)} /> : null}
    <div className="semantic-layout">
      <aside className="semantic-command">
        <div className="semantic-command-heading"><span><Sparkles aria-hidden /></span><div><h2>{t("askAegis")}</h2><p>{t("naturalLanguageHint")}</p></div></div>
        <form onSubmit={(event) => { event.preventDefault(); submit(); }} className="semantic-search-form"><label className="sr-only" htmlFor="evidence-query">{t("searchPlaceholder")}</label><Search aria-hidden /><input id="evidence-query" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={t("searchInputPlaceholder")}/><button type="submit" disabled={draft.trim().length < 3 || search.isFetching}>{search.isFetching ? <LoaderCircle className="animate-spin" /> : <Search />}<span>{search.isFetching ? t("searchingBtn") : t("searchBtn")}</span></button></form>
        <p className="semantic-small-label">{t("quickQueries")}</p><div className="semantic-quick-queries">{quickQueries.map((query) => <button key={query} type="button" onClick={() => submit(query)}>{query}</button>)}</div>
        <SearchFilters request={request} range={searchParams.get("time") ?? "all"} cameras={cameras.data?.cameras ?? []} eventTypes={index.data?.event_types ?? []} disabled={cameras.isError || index.isError} onChange={setParams} onReset={reset} />
      </aside>
      <main className="semantic-results-panel"><SearchResults active={active} search={search} selectedId={selected?.event_id ?? null} onSelect={(id) => { setSelectedId(id); setTab("insights"); }} onPage={(page) => setParams({ page: String(page) })} onSort={(sort) => setParams({ sort })} /></main>
      <aside className="semantic-preview-panel"><EvidencePreview result={selected} detail={detail.data} detailLoading={detail.isLoading} tab={tab} onTab={setTab} locale={locale} onSimilar={(eventId) => { setDraft(""); setSelectedId(null); setParams({ q: null, similar: eventId }); }} /></aside>
    </div>
  </section>;
}

function SemanticStatus({ index, indexLoading, online, total, camerasLoading, detectionRunning }: { index?: ReturnType<typeof useEvidenceSearchStatusQuery>["data"]; indexLoading: boolean; online?: number; total?: number; camerasLoading: boolean; detectionRunning?: boolean }) {
  const t = useTranslations("semantic");
  const cards = [
    { label: t("searchEngine"), value: indexLoading ? t("checking") : index?.state === "ready" ? t("ready") : index?.state === "indexing" ? t("indexing") : t("unavailable"), tone: index?.state },
    { label: t("liveCameras"), value: camerasLoading ? t("checking") : typeof online === "number" && typeof total === "number" ? t("onlineOfTotal", { online, total }) : t("unavailable"), tone: online ? "ready" : "offline" },
    { label: t("lastSync"), value: index?.last_sync ? relativeTime(index.last_sync, t) : index?.state === "indexing" ? t("indexing") : t("unavailable"), tone: index?.state },
    { label: t("detectionService"), value: detectionRunning === undefined ? t("checking") : detectionRunning ? t("running") : t("unavailable"), tone: detectionRunning ? "ready" : "offline" }
  ];
  return <div className="semantic-status-strip">{cards.map((card) => <div key={card.label}><span className={cn("semantic-status-dot", card.tone === "ready" && "is-ready", card.tone === "indexing" && "is-indexing")} /><span><small>{card.label}</small><strong>{card.value}</strong></span></div>)}</div>;
}

function SearchFilters({ request, range, cameras, eventTypes, disabled, onChange, onReset }: { request: EvidenceSearchRequest; range: string; cameras: { camera_id: string; name?: string | null }[]; eventTypes: string[]; disabled: boolean; onChange: (values: Record<string, string | null>) => void; onReset: () => void }) {
  const t = useTranslations("semantic");
  return <details className="semantic-filters" open><summary><span><SlidersHorizontal />{t("advancedFilters")}</span><span>⌄</span></summary><div>
    <FilterSelect label={t("timeRange")} value={range} onChange={(value) => onChange({ time: value === "all" ? null : value })} options={[["all", t("allTime")], ["hour", t("lastHour")], ["day", t("last24h")], ["week", t("last7d")]]} />
    <FilterSelect label={t("camera")} disabled={disabled} value={request.camera_id ?? ""} onChange={(value) => onChange({ camera: value || null })} options={[["", t("allCameras")], ...cameras.map((camera) => [camera.camera_id, camera.name || camera.camera_id])]} />
    <FilterSelect label={t("eventType")} disabled={disabled} value={request.event_type ?? ""} onChange={(value) => onChange({ type: value || null })} options={[["", t("allEventTypes")], ...eventTypes.map((type) => [type, humanize(type)])]} />
    <FilterSelect label={t("riskLevel")} value={request.risk_level ?? ""} onChange={(value) => onChange({ risk: value || null })} options={[["", t("allLevels")], ["LOW", t("low")], ["MEDIUM", t("medium")], ["HIGH", t("high")], ["CRITICAL", t("critical")]]} />
    <label className="semantic-confidence"><span>{t("detectionConfidence")}</span><input type="range" min="0" max="1" step="0.1" value={request.min_confidence} onChange={(event) => onChange({ confidence: event.target.value === "0" ? null : event.target.value })}/><output>{request.min_confidence ? `≥ ${Math.round(request.min_confidence * 100)}%` : t("any")}</output></label>
    <button type="button" onClick={onReset} className="semantic-reset">{t("resetFilters")}</button>
  </div></details>;
}

function FilterSelect({ label, value, options, disabled, onChange }: { label: string; value: string; options: string[][]; disabled?: boolean; onChange: (value: string) => void }) { return <label className="semantic-filter-select"><span>{label}</span><select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>; }

function SearchResults({ active, search, selectedId, onSelect, onPage, onSort }: { active: boolean; search: ReturnType<typeof useEvidenceSearchQuery>; selectedId: string | null; onSelect: (id: string) => void; onPage: (page: number) => void; onSort: (sort: string) => void }) {
  const t = useTranslations("semantic");
  if (!active) return <EmptyResults title={t("searchYourEvidence")} text={t("searchYourEvidenceHint")} icon={FileSearch} />;
  if (search.isLoading || search.isFetching) return <ResultsSkeleton />;
  if (search.isError) return <ErrorNotice message={getErrorMessage(search.error)} />;
  const data = search.data!;
  if (!data.results.length) return <EmptyResults title={t("noEvidence")} text={t("noEvidenceHint")} icon={Search} />;
  return <section className="semantic-results"><header><div><p>{t("searchResults")}</p><h2>{data.total} {data.total === 1 ? t("result") : t("results")}</h2></div><label>{t("sort")}<select value={data.sort ?? "relevance"} onChange={(event) => onSort(event.target.value)}><option value="relevance">{t("relevance")}</option><option value="newest">{t("newest")}</option><option value="oldest">{t("oldest")}</option><option value="risk">{t("highestRisk")}</option><option value="confidence">{t("highestConfidence")}</option></select></label></header>
    {data.pending_evidence ? <p className="semantic-indexing-note">{t("stillIndexing", { count: data.pending_evidence })}</p> : null}
    <div className="semantic-result-list">{data.results.map((result) => <ResultRow key={result.event_id} result={result} selected={result.event_id === selectedId} onClick={() => onSelect(result.event_id)} />)}</div><Pagination data={data} onPage={onPage} />
  </section>;
}

function ResultRow({ result, selected, onClick }: { result: EvidenceSearchResponse["results"][number]; selected: boolean; onClick: () => void }) { const t = useTranslations("semantic"); return <button type="button" className={cn("semantic-result-row", selected && "is-selected")} onClick={onClick}><span className="semantic-result-icon"><Camera /></span><span className="semantic-result-copy"><span className="semantic-result-title">{eventTitle(result, t)}</span><span>{result.camera_name || result.camera_id || t("cameraUnavailable")}{result.zone_name ? ` · ${result.zone_name}` : ""}</span><span>{result.timestamp ? formatTime(result.timestamp) : t("timeUnavailable")}</span></span><span className="semantic-result-values"><span>{result.risk_level ? humanize(result.risk_level) : t("unclassified")}</span>{typeof result.similarity === "number" ? <strong>{t("match", { value: Math.round(result.similarity * 100) })}</strong> : null}</span></button>; }

function Pagination({ data, onPage }: { data: EvidenceSearchResponse; onPage: (page: number) => void }) { const t = useTranslations("semantic"); const start = (data.page - 1) * data.page_size + 1; const end = start + data.results.length - 1; return <footer className="semantic-pagination"><span>{t("ofTotal", { start, end, total: data.total })}</span><div><button disabled={!data.has_previous} onClick={() => onPage(data.page - 1)} aria-label={t("previousPage")}><ChevronLeft /></button><button disabled={!data.has_next} onClick={() => onPage(data.page + 1)} aria-label={t("nextPage")}><ChevronRight /></button></div></footer>; }

function EvidencePreview({ result, detail, detailLoading, tab, onTab, locale, onSimilar }: { result: EvidenceSearchResponse["results"][number] | null; detail?: ReturnType<typeof useEvidenceSearchDetailQuery>["data"]; detailLoading: boolean; tab: Tab; onTab: (tab: Tab) => void; locale: string; onSimilar: (eventId: string) => void }) {
  const t = useTranslations("semantic");
  if (!result) return <section className="semantic-preview-empty"><Database /><h2>{t("selectEvidence")}</h2><p>{t("selectEvidenceHint")}</p></section>;
  const evidence = detail?.evidence ?? result;
  return <section className="semantic-preview"><header><div><p>{t("evidencePreview")}</p><h2>{eventTitle(evidence, t)}</h2></div><span>{evidence.risk_level ? humanize(evidence.risk_level) : t("unclassified")}</span></header>
    <EvidenceMedia evidence={evidence} />
    <div className="semantic-preview-facts"><span><small>{t("cameraLabel")}</small>{evidence.camera_name || evidence.camera_id || t("unavailable")}</span><span><small>{t("captured")}</small>{evidence.timestamp ? formatTime(evidence.timestamp) : t("unavailable")}</span></div>
    <div className="semantic-preview-actions"><Link href={`/${locale}/events`}><ExternalLink />{t("viewEvidence")}</Link><button type="button" onClick={() => onSimilar(evidence.event_id)} disabled={detailLoading}><Search />{t("findSimilar")}</button></div>
    <div className="semantic-tabs" role="tablist">{(["insights", "metadata", "related", "entities"] as Tab[]).map((name) => <button key={name} role="tab" aria-selected={tab === name} onClick={() => onTab(name)}>{name === "insights" ? t("aiInsights") : name === "related" ? t("relatedEvidence") : name === "entities" ? t("linkedEntities") : t("metadata")}</button>)}</div>
    <EvidenceTab tab={tab} evidence={evidence} related={detail?.related ?? []} onSelectRelated={onSimilar} />
  </section>;
}

function EvidenceMedia({ evidence }: { evidence: EvidenceSearchResponse["results"][number] }) {
  const t = useTranslations("semantic");
  if (!evidence.snapshot_available) return <div className="semantic-evidence-empty"><Camera /><span>{t("noSnapshot")}</span></div>;
  return <div className="semantic-evidence-media">
    {/* Snapshot access is authenticated by the backend and cannot be optimized through an unauthenticated image loader. */}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img src={`${appConfig.apiUrl}/events/evidence/${encodeURIComponent(evidence.event_id)}/snapshot`} alt={t("savedEvidenceAlt", { camera: evidence.camera_name || evidence.camera_id || t("camera") })} />
    <span>{t("savedEvidence")}</span>
  </div>;
}

function EvidenceTab({ tab, evidence, related, onSelectRelated }: { tab: Tab; evidence: EvidenceSearchResponse["results"][number]; related: EvidenceSearchResponse["results"]; onSelectRelated: (eventId: string) => void }) { const t = useTranslations("semantic"); if (tab === "insights") return <div className="semantic-tab-panel"><h3>{t("whyThisResult")}</h3><p>{insight(evidence, t)}</p>{typeof evidence.similarity === "number" ? <span>{t("semanticMatch")} <strong>{evidence.similarity.toFixed(2)}</strong></span> : null}{typeof evidence.detection_confidence === "number" ? <span>{t("detectionConfidence")} <strong>{Math.round(evidence.detection_confidence * 100)}%</strong></span> : null}</div>; if (tab === "metadata") return <dl className="semantic-metadata">{metadata(evidence, t).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>; if (tab === "related") return <div className="semantic-related">{related.length ? related.map((item) => <button type="button" onClick={() => onSelectRelated(item.event_id)} key={item.event_id}><span>{eventTitle(item, t)}</span><small>{item.timestamp ? formatTime(item.timestamp) : t("timeUnavailable")}</small></button>) : <p>{t("noRelatedEvidence")}</p>}</div>; return <div className="semantic-entities">{entityLinks(evidence, t).map(([label, href]) => href ? <Link key={label} href={href}><Tag />{label}<ExternalLink /></Link> : <span key={label}><Tag />{label}</span>)}</div>; }

function EmptyResults({ title, text, icon: Icon }: { title: string; text: string; icon: typeof Search }) { return <section className="semantic-empty-results"><Icon /><h2>{title}</h2><p>{text}</p></section>; }
function ResultsSkeleton() { const t = useTranslations("semantic"); return <section className="semantic-skeleton" aria-label={t("searching")} aria-busy="true"><div/><div/><div/><div/></section>; }
function ErrorNotice({ message }: { message: string }) { const t = useTranslations("semantic"); return <section className="semantic-error"><WifiOff /><div><h2>{t("evidenceSearchUnavailable")}</h2><p>{message}</p></div></section>; }
function eventTitle(item: EvidenceSearchResponse["results"][number], t: ReturnType<typeof useTranslations>) { return item.reason || [item.object_class && humanize(item.object_class), item.event_type && humanize(item.event_type)].filter(Boolean).join(" · ") || t("storedEvidence"); }
function humanize(value: string) { return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function relativeTime(value: string, t: ReturnType<typeof useTranslations>) { const delta = Date.now() - Date.parse(value); if (!Number.isFinite(delta)) return t("unavailable"); if (delta < 60_000) return t("justNow"); if (delta < 3_600_000) return t("minutesAgo", { count: Math.floor(delta / 60_000) }); if (delta < 86_400_000) return t("hoursAgo", { count: Math.floor(delta / 3_600_000) }); return formatTime(value); }
function insight(evidence: EvidenceSearchResponse["results"][number], t: ReturnType<typeof useTranslations>) { const subject = evidence.object_class ? t("recordedSubject", { subject: humanize(evidence.object_class).toLowerCase() }) : t("evidenceRecorded"); const location = evidence.zone_name || evidence.zone; const risk = evidence.risk_level ? t("classifiedRisk", { risk: humanize(evidence.risk_level).toLowerCase() }) : ""; return `${subject}${location ? t("atLocation", { location }) : ""}${risk}. ${evidence.reason || t("rankingReason")}`; }
function metadata(evidence: EvidenceSearchResponse["results"][number], t: ReturnType<typeof useTranslations>): [string, string][] { const unavailable = t("unavailable"); return [[t("evidenceId"), evidence.event_id], [t("event"), evidence.event_type ? humanize(evidence.event_type) : unavailable], [t("camera"), evidence.camera_id || unavailable], [t("captured"), evidence.timestamp || unavailable], [t("object"), evidence.object_class ? humanize(evidence.object_class) : unavailable], [t("track"), evidence.track_id ? String(evidence.track_id) : unavailable], [t("zone"), evidence.zone_name || evidence.zone || unavailable], [t("riskScore"), typeof evidence.risk_score === "number" ? evidence.risk_score.toFixed(2) : unavailable], [t("detectors"), evidence.detectors.length ? evidence.detectors.join(", ") : unavailable]]; }
function entityLinks(evidence: EvidenceSearchResponse["results"][number], t: ReturnType<typeof useTranslations>): [string, string | null][] { return [[evidence.camera_name || evidence.camera_id || t("cameraUnavailable"), evidence.camera_id ? `/cameras?camera=${encodeURIComponent(evidence.camera_id)}&view=focus` : null], [evidence.incident_id ? t("incident", { id: evidence.incident_id }) : t("noLinkedIncident"), null], [evidence.track_id ? t("trackEntity", { id: evidence.track_id }) : t("noLinkedTrack"), evidence.track_id ? "/tracks" : null]]; }
