"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Activity, AlertTriangle, BarChart3, Camera, CheckCircle2, CircleAlert, Database, ExternalLink, Gauge, Radar, ShieldAlert, ShieldCheck, Users, Video, Wifi, WifiOff } from "lucide-react";

import { AnalyticsChart } from "@/components/analytics/analytics-chart";
import { RiskBadge } from "@/components/dashboard/risk-badge";
import { Badge } from "@/components/ui/badge";
import { analyticsCoverage, cameraRiskRanking, eventTypeBreakdown, type AnalyticsCoverageItem } from "@/lib/analytics-adapter";
import { alertsBySeverityData, crowdDensityTrendData, detectionsOverTimeData, formatDecimal, formatNumber, formatTimestamp, getCrowdMetric, riskDistributionData } from "@/lib/data-format";
import { cn } from "@/lib/utils";
import type { Camera as CameraType, OperationalAlert, StatisticsResponse } from "@/types";

type RiskAnalyticsWorkspaceProps = {
  statistics?: StatisticsResponse;
  activeAlerts?: OperationalAlert[];
  activeAlertCount?: number;
  cameras: CameraType[];
  statisticsLoading: boolean;
  statisticsUnavailable: boolean;
  alertsUnavailable: boolean;
  camerasUnavailable: boolean;
  evidenceAvailable: boolean;
  evidenceUnavailable: boolean;
  dataUpdatedAt?: number;
  onRetry: () => void;
};

export function RiskAnalyticsWorkspace({
  statistics,
  activeAlerts,
  activeAlertCount,
  cameras,
  statisticsLoading,
  statisticsUnavailable,
  alertsUnavailable,
  camerasUnavailable,
  evidenceAvailable,
  evidenceUnavailable,
  dataUpdatedAt,
  onRetry,
}: RiskAnalyticsWorkspaceProps) {
  const t = useTranslations("analytics");
  const onlineCameras = cameras.filter((camera) => camera.runtime.status === "online").length;
  const offlineCameras = cameras.filter((camera) => ["offline", "error", "failed"].includes(camera.runtime.status)).length;
  const highCriticalAlerts = activeAlerts?.filter((alert) => ["HIGH", "CRITICAL"].includes(alert.risk_level.toUpperCase())).length;
  const coverage = analyticsCoverage(statistics, { camerasAvailable: !camerasUnavailable, evidenceAvailable, evidenceDegraded: evidenceUnavailable });
  const ranking = cameraRiskRanking(statistics?.latest_detection_events ?? [], cameras);
  const eventTypes = eventTypeBreakdown(statistics);
  const attention = buildAttention({ statistics, activeAlerts, highCriticalAlerts, offlineCameras, alertsUnavailable, camerasUnavailable, evidenceUnavailable, coverage, statisticsUnavailable, t });
  const backendState = statisticsUnavailable ? "unavailable" : alertsUnavailable || camerasUnavailable || evidenceUnavailable ? "degraded" : "connected";

  if (statisticsLoading && !statistics) return <AnalyticsLoadingState />;

  return (
    <section className="mx-auto w-full max-w-[1800px] px-4 py-7 sm:px-6 lg:px-8" aria-labelledby="risk-analytics-title">
      <header className="flex flex-col gap-5 border-b border-white/[0.08] pb-6 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-signal-cyan">{t("commandAnalytics")}</p>
          <h1 id="risk-analytics-title" className="mt-2 text-3xl font-semibold tracking-tight text-white sm:text-4xl">{t("title")}</h1>
          <p className="mt-2 text-sm text-slate-400 sm:text-base">{t("subtitle")}</p>
        </div>
        <AnalyticsStatusChips backendState={backendState} dataUpdatedAt={dataUpdatedAt} t={t} />
      </header>

      {statisticsUnavailable ? <StatisticsUnavailable onRetry={onRetry} t={t} /> : null}

      <section className="mt-6" aria-labelledby="risk-summary-title">
        <div className="mb-3 flex items-center gap-2"><Radar className="h-4 w-4 text-signal-cyan" aria-hidden /><h2 id="risk-summary-title" className="text-lg font-semibold text-white">{t("executiveSummary")}</h2></div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
          <MetricCard t={t} label={t("activeAlertsLabel")} value={metricValue(activeAlertCount, alertsUnavailable, t)} icon={ShieldAlert} tone={highCriticalAlerts ? "danger" : "cyan"} />
          <MetricCard t={t} label={t("highCriticalLabel")} value={metricValue(highCriticalAlerts, alertsUnavailable, t)} icon={AlertTriangle} tone={highCriticalAlerts ? "danger" : "warning"} />
          <MetricCard t={t} label={t("personsDetected")} value={metricValue(crowdValue(statistics, "person_count"), !statistics, t)} icon={Users} tone="cyan" />
          <MetricCard t={t} label={t("vehiclesDetected")} value={metricValue(crowdValue(statistics, "vehicle_count"), !statistics, t)} icon={Video} tone="cyan" />
          <MetricCard t={t} label={t("maxCrowdDensity")} value={metricDecimal(crowdValue(statistics, "max_density"), !statistics, t)} icon={Gauge} tone="cyan" />
          <MetricCard t={t} label={t("camerasOnlineLabel")} value={metricValue(camerasUnavailable ? undefined : onlineCameras, camerasUnavailable, t)} icon={Camera} tone={offlineCameras ? "warning" : "cyan"} />
        </div>
      </section>

      <AttentionPanel items={attention} t={t} />

      {statistics ? <>
        <section className="mt-6 grid gap-5 xl:grid-cols-2" aria-label="Analytics charts">
          <AnalyticsChart title={t("alertsBySeverity")} description={t("reportedOperatorAlertLevels")} data={alertsBySeverityData(statistics)} kind="bar" xKey="severity" yKey="count" color="#38d6ff" emptyTitle={t("noSeverityDistribution")} emptyDescription={t("alertSeverityNotReturned")} />
          <AnalyticsChart title={t("riskLevelDistribution")} description={t("currentReportedRiskScores")} data={riskDistributionData(statistics)} kind="pie" xKey="level" yKey="count" emptyTitle={t("noRiskDistribution")} emptyDescription={t("riskDistributionNotReturned")} />
          <AnalyticsChart title={t("detectionsOverTime")} description={t("historicalDetectionActivity")} data={detectionsOverTimeData(statistics)} kind="line" xKey="time" yKey="detections" color="#38d6ff" emptyTitle={t("noTimelineData")} emptyDescription={t("connectEventHistory")} />
          <AnalyticsChart title={t("crowdDensityTrend")} description={t("historicalCrowdMeasurement")} data={crowdDensityTrendData(statistics)} kind="line" xKey="time" yKey="density" color="#2dd4bf" emptyTitle={t("noTimelineData")} emptyDescription={t("connectEventHistory")} />
        </section>

        <section className="mt-6 grid gap-5 2xl:grid-cols-[minmax(0,1.4fr)_minmax(360px,0.7fr)]">
          <CameraRiskRanking rows={ranking} camerasUnavailable={camerasUnavailable} t={t} />
          <EventTypeBreakdown items={eventTypes} t={t} />
        </section>
      </> : null}

      <AnalyticsCoveragePanel coverage={coverage} t={t} />
    </section>
  );
}

function AnalyticsStatusChips({ backendState, dataUpdatedAt, t }: { backendState: "connected" | "degraded" | "unavailable"; dataUpdatedAt?: number; t: any }) {
  const lastUpdated = typeof dataUpdatedAt === "number" && Number.isFinite(dataUpdatedAt)
    ? new Date(dataUpdatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : t("updateTimeUnavailable");
  const statusValue = backendState === "connected" ? t("connected") : backendState === "degraded" ? t("degraded") : t("unavailable");
  return <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:justify-end">
    <StatusChip label={t("dataSource")} value={t("liveOperationalData")} tone="cyan" icon={Database} />
    <StatusChip label={t("lastUpdate")} value={lastUpdated} tone="neutral" icon={Activity} />
    <StatusChip label={t("systemConnection")} value={statusValue} tone={backendState === "connected" ? "success" : backendState === "degraded" ? "warning" : "danger"} icon={backendState === "connected" ? Wifi : WifiOff} />
    <StatusChip label={t("mode")} value={t("snapshotMode")} tone="neutral" icon={BarChart3} />
  </div>;
}

function StatusChip({ label, value, tone, icon: Icon }: { label: string; value: string; tone: "cyan" | "success" | "warning" | "danger" | "neutral"; icon: typeof Database }) {
  return <div className="min-w-[132px] rounded-lg border border-white/[0.1] bg-white/[0.025] px-3 py-2.5"><div className="flex items-center gap-2 text-xs text-slate-400"><Icon className="h-3.5 w-3.5" aria-hidden />{label}</div><p className={cn("mt-1 flex items-center gap-1.5 text-sm font-medium", tone === "cyan" ? "text-signal-cyan" : tone === "success" ? "text-emerald-200" : tone === "warning" ? "text-amber-100" : tone === "danger" ? "text-rose-200" : "text-slate-200")}><span className={cn("h-2 w-2 rounded-full", tone === "cyan" ? "bg-signal-cyan" : tone === "success" ? "bg-emerald-400" : tone === "warning" ? "bg-amber-300" : tone === "danger" ? "bg-rose-400" : "bg-slate-500")} aria-hidden />{value}</p></div>;
}

function MetricCard({ label, value, icon: Icon, tone, t }: { label: string; value: string; icon: typeof ShieldAlert; tone: "cyan" | "warning" | "danger"; t: any }) {
  return <article className={cn("rounded-xl border p-4", tone === "danger" ? "border-eose-400/25 bg-rose-400/[0.055]" : tone === "warning" ? "border-amber-300/25 bg-amber-300/[0.045]" : "border-white/[0.1] bg-white/[0.025]")}><div className="flex items-center justify-between gap-3"><span className={cn("flex h-9 w-9 items-center justify-center rounded-lg border", tone === "danger" ? "border-eose-300/40 text-rose-200" : tone === "warning" ? "border-amber-300/40 text-amber-100" : "border-signal-cyan/35 bg-signal-cyan/[0.07] text-signal-cyan")}><Icon className="h-4.5 w-4.5" aria-hidden /></span><span className="text-xs text-slate-500">{t("liveValue")}</span></div><p className="mt-4 text-2xl font-semibold tracking-tight text-white">{value}</p><p className="mt-1 text-sm text-slate-400">{label}</p></article>;
}

function AttentionPanel({ items, t }: { items: AttentionItem[]; t: any }) {
  return <section className="mt-6 rounded-xl border border-white/[0.1] bg-white/[0.025] p-5 sm:p-6" aria-labelledby="attention-title"><div className="flex items-center gap-2"><CircleAlert className="h-4.5 w-4.5 text-amber-200" aria-hidden /><h2 id="attention-title" className="text-lg font-semibold text-white">{t("needsAttention")}</h2></div>{items.length ? <div className="mt-4 grid gap-3 lg:grid-cols-2">{items.map((item) => <div key={item.title} className={cn("flex items-start gap-3 rounded-lg border p-3", item.tone === "danger" ? "border-eose-400/25 bg-rose-400/[0.05]" : "border-amber-300/20 bg-amber-300/[0.04]")}><AlertTriangle className={cn("mt-0.5 h-4 w-4 shrink-0", item.tone === "danger" ? "text-rose-200" : "text-amber-100")} aria-hidden /><div><p className="text-sm font-medium text-slate-100">{item.title}</p><p className="mt-1 text-sm text-slate-400">{item.detail}</p></div></div>)}</div> : <div className="mt-4 flex items-center gap-3 rounded-lg border border-emerald-300/20 bg-emerald-400/[0.045] px-4 py-3"><CheckCircle2 className="h-5 w-5 text-emerald-300" aria-hidden /><p className="text-sm font-medium text-emerald-100">{t("systemAnalyticsStable")}</p></div>}</section>;
}

function CameraRiskRanking({ rows, camerasUnavailable, t }: { rows: ReturnType<typeof cameraRiskRanking>; camerasUnavailable: boolean; t: any }) {
  return <section className="overflow-hidden rounded-xl border border-white/[0.1] bg-white/[0.025]" aria-labelledby="camera-ranking-title"><div className="border-b border-white/[0.08] px-5 py-5 sm:px-6"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-signal-cyan">{t("recentActivity")}</p><h2 id="camera-ranking-title" className="mt-1 text-xl font-semibold tracking-tight text-white">{t("cameraRiskRanking")}</h2><p className="mt-1 text-sm text-slate-400">{t("basedOnRecentActivity")}</p></div>{camerasUnavailable ? <PanelEmpty t={t} title={t("cameraStatusUnavailable")} description={t("cameraStatusUnavailableDesc")} /> : rows.length ? <div className="divide-y divide-white/[0.08]">{rows.map((row) => <article key={row.cameraId} className="grid gap-3 px-5 py-4 sm:px-6 lg:grid-cols-[minmax(0,1.2fr)_auto_auto_auto_auto] lg:items-center"><div className="min-w-0"><p className="truncate text-sm font-semibold text-white">{row.cameraName}</p><p className="mt-1 font-mono text-xs text-slate-500">{row.cameraId}</p></div><CameraStatus status={row.runtimeStatus} t={t} /><p className="text-sm text-slate-300"><span className="text-slate-500">{t("recentAlerts")} </span>{row.recentAlertCount}</p><div>{row.highestRisk ? <RiskBadge level={row.highestRisk} /> : <Badge variant="outline">Unavailable</Badge>}<p className="mt-1 text-xs text-slate-500">{row.lastEventTime ? formatTimestamp(row.lastEventTime) : t("lastEventUnavailable")}</p></div><Link href={`/cameras?camera=${encodeURIComponent(row.cameraId)}&view=focus`} className="inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-white/[0.12] px-3 text-sm font-medium text-slate-200 transition hover:border-signal-cyan/45 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-cyan"><Camera className="h-4 w-4" aria-hidden />{t("openCamera")}<ExternalLink className="h-3.5 w-3.5" aria-hidden /></Link></article>)}</div> : <PanelEmpty t={t} title={t("cameraRankingUnavailable")} description={t("noRecentCameraActivity")} />}</section>;
}

function EventTypeBreakdown({ items, t }: { items: ReturnType<typeof eventTypeBreakdown>; t: any }) {
  return <section className="rounded-xl border border-white/[0.1] bg-white/[0.025] p-5 sm:p-6" aria-labelledby="event-breakdown-title"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-signal-cyan">{t("recentActivity")}</p><h2 id="event-breakdown-title" className="mt-1 text-xl font-semibold tracking-tight text-white">{t("eventTypeBreakdown")}</h2><p className="mt-1 text-sm text-slate-400">{t("typesOfRecentSecurityActivity")}</p>{items.length ? <div className="mt-5 space-y-3">{items.map((item) => <div key={item.eventType} className="flex items-center justify-between gap-3 rounded-lg border border-white/[0.08] bg-black/[0.16] px-3 py-3"><div className="min-w-0"><p className="truncate text-sm font-medium text-slate-200">{item.label}</p><p className="mt-1 font-mono text-xs text-slate-500">{item.eventType}</p></div><span className="text-xl font-semibold text-signal-cyan">{formatNumber(item.count)}</span></div>)}</div> : <PanelEmpty t={t} title={t("eventTypeDataUnavailable")} description={t("noActivityTypesAvailable")} />}</section>;
}

function AnalyticsCoveragePanel({ coverage, t }: { coverage: AnalyticsCoverageItem[]; t: any }) {
  return <section className="mt-6 rounded-xl border border-white/[0.1] bg-white/[0.025] p-5 sm:p-6" aria-labelledby="coverage-title"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-signal-cyan">{t("dataQuality")}</p><h2 id="coverage-title" className="mt-1 text-xl font-semibold tracking-tight text-white">{t("analyticsCoverage")}</h2></div><p className="text-sm text-slate-400">{t("whatIsCurrentlyAvailable")}</p></div><div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{coverage.map((item) => <div key={item.label} className="rounded-lg border border-white/[0.08] bg-black/[0.14] p-3"><div className="flex items-center justify-between gap-2"><p className="text-sm font-medium text-slate-200">{item.label}</p><CoverageBadge status={item.status} t={t} /></div><p className="mt-2 text-xs leading-5 text-slate-500">{item.detail}</p></div>)}</div></section>;
}

function CameraStatus({ status, t }: { status: CameraType["runtime"]["status"] | null; t: any }) {
  const copy = status === "online" ? "Online" : status ? status.replace(/_/g, " ") : t("unavailable");
  const tone = status === "online" ? "success" : ["offline", "error", "failed"].includes(status ?? "") ? "danger" : "outline";
  return <Badge variant={tone}>{copy}</Badge>;
}

function CoverageBadge({ status, t }: { status: AnalyticsCoverageItem["status"]; t: any }) {
  const variant = status === "available" ? "success" : status === "degraded" ? "warning" : status === "missing" ? "outline" : "default";
  const label = status === "available" ? "Available" : status === "degraded" ? t("degraded") : status === "missing" ? t("unavailable") : "Not confirmed";
  return <Badge variant={variant}>{label}</Badge>;
}

function PanelEmpty({ title, description, t }: { title: string; description: string; t?: any }) {
  return <div className="flex min-h-48 flex-col items-center justify-center px-6 text-center"><Database className="h-7 w-7 text-slate-600" aria-hidden /><p className="mt-3 text-sm font-medium text-slate-200">{title}</p><p className="mt-1 max-w-md text-sm text-slate-500">{description}</p></div>;
}

function StatisticsUnavailable({ onRetry, t }: { onRetry: () => void; t: any }) {
  return <section className="mt-6 rounded-xl border border-eose-400/25 bg-rose-500/[0.06] px-5 py-4"><div className="flex items-start gap-3"><WifiOff className="mt-0.5 h-5 w-5 shrink-0 text-rose-300" aria-hidden /><div><h2 className="text-sm font-semibold text-rose-100">{t("riskAnalyticsUnavailable")}</h2><p className="mt-1 text-sm text-rose-100/75">{t("currentAnalyticsNotLoaded")}</p><button type="button" onClick={onRetry} className="mt-3 inline-flex min-h-9 rounded-md border border-eose-300/35 px-3 text-sm font-medium text-rose-100 transition hover:bg-rose-400/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-200">{t("retry")}</button></div></div></section>;
}

function AnalyticsLoadingState() {
  return <section className="mx-auto w-full max-w-[1800px] px-4 py-7 sm:px-6 lg:px-8" aria-busy="true" aria-label="Loading risk analytics"><div className="h-10 w-64 animate-pulse rounded bg-white/[0.07]" /><div className="mt-3 h-5 w-96 max-w-full animate-pulse rounded bg-white/[0.04]" /><div className="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">{Array.from({ length: 6 }).map((_, index) => <div key={index} className="h-32 animate-pulse rounded-xl border border-white/[0.1] bg-white/[0.025]" />)}</div><div className="mt-6 h-44 animate-pulse rounded-xl border border-white/[0.1] bg-white/[0.025]" /><div className="mt-6 grid gap-5 xl:grid-cols-2">{Array.from({ length: 4 }).map((_, index) => <div key={index} className="h-[300px] animate-pulse rounded-xl border border-white/[0.1] bg-white/[0.025]" />)}</div></section>;
}

type AttentionItem = { title: string; detail: string; tone: "warning" | "danger" };

function buildAttention({ statistics, activeAlerts, highCriticalAlerts, offlineCameras, alertsUnavailable, camerasUnavailable, evidenceUnavailable, coverage, statisticsUnavailable, t }: { statistics?: StatisticsResponse; activeAlerts?: OperationalAlert[]; highCriticalAlerts?: number; offlineCameras: number; alertsUnavailable: boolean; camerasUnavailable: boolean; evidenceUnavailable: boolean; coverage: AnalyticsCoverageItem[]; statisticsUnavailable: boolean; t: any }) {
  const items: AttentionItem[] = [];
  if (statisticsUnavailable) items.push({ title: t("buildAttention.riskAnalyticsUnavailable"), detail: t("buildAttention.currentAnalyticsNotLoaded"), tone: "danger" });
  if (alertsUnavailable) items.push({ title: t("buildAttention.activeAlertDataUnavailable"), detail: t("buildAttention.currentAlertCountsNotVerified"), tone: "warning" });
  else if (highCriticalAlerts && highCriticalAlerts > 0) items.push({ title: highCriticalAlerts === 1 ? t("buildAttention.activeAlertsMsg", { count: highCriticalAlerts }) : t("buildAttention.activeAlertsMsgPlural", { count: highCriticalAlerts }), detail: t("buildAttention.reviewActiveOperatorAlerts"), tone: "danger" });
  if (camerasUnavailable) items.push({ title: t("buildAttention.cameraStatusUnavailable"), detail: t("buildAttention.offlineCameraCountsNotVerified"), tone: "warning" });
  else if (offlineCameras > 0) items.push({ title: offlineCameras === 1 ? t("buildAttention.offlineCameraMsg", { count: offlineCameras }) : t("buildAttention.offlineCameraMsgPlural", { count: offlineCameras }), detail: t("buildAttention.checkCameraConnection"), tone: "warning" });
  if (statistics?.model?.weapon_detection_supported === false) items.push({ title: t("buildAttention.weaponDetectionUnavailable"), detail: t("buildAttention.weaponActivityNotAssessed"), tone: "warning" });
  if (evidenceUnavailable) items.push({ title: t("buildAttention.savedEvidenceStatusUnavailable"), detail: t("buildAttention.evidenceAvailabilityNotVerified"), tone: "warning" });
  const missingCount = coverage.filter((item) => item.status === "missing").length;
  if (missingCount > 0) items.push({ title: missingCount === 1 ? t("buildAttention.analyticsCapabilityUnavailable") : t("buildAttention.analyticsCapabilitiesUnavailable", { count: missingCount }), detail: t("buildAttention.seeAnalyticsCoverage"), tone: "warning" });
  return items;
}

function crowdValue(statistics: StatisticsResponse | undefined, key: "person_count" | "vehicle_count" | "max_density") {
  const crowdMetric = getCrowdMetric(statistics, key);
  if (typeof crowdMetric === "number" && Number.isFinite(crowdMetric)) return crowdMetric;
  return key === "person_count" ? statistics?.detections?.people_count : key === "vehicle_count" ? statistics?.detections?.vehicles_count : undefined;
}

function metricValue(value: number | undefined, unavailable: boolean, t: any) {
  return unavailable || value === undefined ? t("unavailable") : formatNumber(value);
}

function metricDecimal(value: number | undefined, unavailable: boolean, t: any) {
  return unavailable || value === undefined ? t("unavailable") : formatDecimal(value, 1);
}
