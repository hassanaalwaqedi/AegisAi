"use client";

import { useMemo } from "react";
import { Link } from "@/i18n/routing";
import { useTranslations } from "next-intl";
import {
  AlertTriangle,
  BellRing,
  Camera,
  CheckCircle2,
  CircleAlert,
  CircleOff,
  ClipboardCheck,
  FileSearch,
  RadioTower,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  WifiOff,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { formatTimestamp, getStatusSystem } from "@/lib/data-format";
import type { Camera as CameraType, EvidenceRecord, Incident, OperationalAlert, RiskEvent, StatusResponse } from "@/types";

type CameraCondition = "live" | "delayed" | "offline" | "unavailable";
type AttentionKind = "alert" | "camera" | "incident" | "detection" | "evidence";
type DashboardSource = "status" | "cameras" | "alerts" | "events" | "incidents" | "evidence";

type DashboardAvailability = Record<DashboardSource, boolean>;

type AttentionItem = {
  id: string;
  kind: AttentionKind;
  priority: number;
  title: string;
  detail: string;
  location?: string;
  timestamp?: string | number | null;
  href: string;
};

type ActivityItem = {
  id: string;
  title: string;
  detail?: string;
  camera?: string;
  timestamp?: string | number | null;
};

type OperatorDashboardProps = {
  cameras: CameraType[];
  events: RiskEvent[];
  alerts?: OperationalAlert[];
  incidents?: Incident[];
  evidence?: EvidenceRecord[];
  status?: StatusResponse;
  availability?: Partial<DashboardAvailability>;
  isLoading: boolean;
  isUnavailable: boolean;
  onRetry: () => void;
};

const CLOSED_INCIDENT_STATES = new Set(["resolved", "closed", "false_positive"]);

function cameraName(camera?: CameraType, cameraId?: string | null) {
  if (camera?.name?.trim()) return camera.name.trim();
  const reference = camera?.camera_id ?? cameraId;
  if (!reference) return "Camera unavailable";
  const numericSuffix = reference.match(/(\d+)$/)?.[1];
  return numericSuffix ? `Camera ${numericSuffix}` : "Camera";
}

function cameraCondition(camera: CameraType): CameraCondition {
  const runtime = camera.runtime;
  if (["offline", "error", "stopped", "failed"].includes(runtime.status)) return "offline";
  if (["connecting", "reconnecting"].includes(runtime.status)) return "delayed";
  if (runtime.status === "online" && runtime.running) return "live";
  return "unavailable";
}

function priorityFromRisk(level?: string | null) {
  const value = String(level ?? "").toUpperCase();
  if (value === "CRITICAL") return 4;
  if (value === "HIGH") return 3;
  if (["MEDIUM", "CANDIDATE_MEDIUM", "WARNING"].includes(value)) return 2;
  return 1;
}

function priorityFromEvent(event: RiskEvent) {
  return priorityFromRisk(event.risk_level ?? event.severity ?? event.level);
}

function eventTime(event?: RiskEvent) {
  return dateValue(event?.timestamp);
}

function dateValue(value?: string | number | null) {
  if (typeof value === "number") return value * 1_000;
  if (typeof value === "string") return Date.parse(value) || 0;
  return 0;
}

function focusHref(cameraId?: string | null) {
  return cameraId ? `/cameras?camera=${encodeURIComponent(cameraId)}&view=focus` : "/cameras";
}

function cameraCounts(cameras: CameraType[]) {
  const conditions = cameras.map(cameraCondition);
  return {
    total: cameras.length,
    live: conditions.filter((condition) => condition === "live").length,
    attention: conditions.filter((condition) => condition === "delayed" || condition === "unavailable").length,
    offline: conditions.filter((condition) => condition === "offline").length,
  };
}

function incidentIsOpen(incident: Incident) {
  return !CLOSED_INCIDENT_STATES.has(incident.status.trim().toLowerCase());
}

function shortText(value: string, maxLength = 116) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1).trimEnd()}…` : value;
}

function buildAttentionItems({ cameras, alerts, events, incidents, status, availability }: {
  cameras: CameraType[];
  alerts?: OperationalAlert[];
  events: RiskEvent[];
  incidents?: Incident[];
  status?: StatusResponse;
  availability: DashboardAvailability;
}) {
  const camerasById = new Map(cameras.map((camera) => [camera.camera_id, camera]));
  const items: AttentionItem[] = [];

  if (availability.alerts && alerts) {
    for (const alert of alerts) {
      if (alert.acknowledged) continue;
      const priority = priorityFromRisk(alert.risk_level);
      if (priority < 2) continue;
      const camera = alert.camera_id ? camerasById.get(alert.camera_id) : undefined;
      const location = [cameraName(camera, alert.camera_name ?? alert.camera_id), alert.zone].filter(Boolean).join(" · ");
      items.push({
        id: `alert:${alert.alert_id}`,
        kind: "alert",
        priority,
        title: priority === 4 ? "Critical alert" : priority === 3 ? "High-priority alert" : "Alert needs review",
        detail: shortText(alert.message || "Security activity requires review."),
        location: location || undefined,
        timestamp: alert.timestamp,
        href: "/events",
      });
    }
  } else if (availability.events) {
    for (const event of events) {
      const priority = priorityFromEvent(event);
      if (priority < 2) continue;
      const camera = event.camera_id ? camerasById.get(event.camera_id) : undefined;
      items.push({
        id: `event:${event.event_id ?? event.id ?? `${event.timestamp}-${event.camera_id}`}`,
        kind: "alert",
        priority,
        title: priority === 4 ? "Critical activity" : priority === 3 ? "High-priority activity" : "Activity needs review",
        detail: shortText(event.explanation ?? event.description ?? event.reason ?? "Security activity requires review."),
        location: cameraName(camera, event.camera_id),
        timestamp: event.timestamp,
        href: "/events",
      });
    }
  }

  if (availability.incidents && incidents) {
    for (const incident of incidents.filter(incidentIsOpen)) {
      const priority = priorityFromRisk(incident.current_risk_level);
      const camera = camerasById.get(incident.camera_id);
      items.push({
        id: `incident:${incident.incident_id}`,
        kind: "incident",
        priority: Math.max(2, priority),
        title: "Open incident",
        detail: shortText(incident.summary_reason ?? "This incident requires operator review."),
        location: cameraName(camera, incident.camera_id),
        timestamp: incident.last_seen_time ?? incident.start_time,
        href: "/events",
      });
    }
  }

  if (availability.cameras) {
    for (const camera of cameras) {
      const condition = cameraCondition(camera);
      if (condition !== "offline" && condition !== "delayed") continue;
      items.push({
        id: `camera:${camera.camera_id}:${condition}`,
        kind: "camera",
        priority: condition === "offline" ? 3 : 2,
        title: condition === "offline" ? "Camera offline" : "Live image delayed",
        detail: condition === "offline" ? "This camera is not currently sending live images." : "This camera is reconnecting or its latest image is delayed.",
        location: cameraName(camera),
        timestamp: camera.runtime.last_frame_time,
        href: focusHref(camera.camera_id),
      });
    }
  }

  if (availability.status && status?.system?.running === false) {
    items.push({
      id: "detection-service",
      kind: "detection",
      priority: 3,
      title: "Detection service needs attention",
      detail: "Current activity cannot be assessed until the service is ready.",
      href: "/intelligence",
    });
  }

  if (!availability.evidence) {
    items.push({
      id: "evidence-unavailable",
      kind: "evidence",
      priority: 2,
      title: "Evidence is unavailable",
      detail: "Saved evidence cannot be loaded right now.",
      href: "/semantic",
    });
  }

  return items.sort((left, right) => right.priority - left.priority || dateValue(right.timestamp) - dateValue(left.timestamp));
}

function buildLatestActivity(alerts: OperationalAlert[] | undefined, events: RiskEvent[], alertsAvailable: boolean) {
  if (alertsAvailable && alerts) {
    return alerts
      .filter((alert) => priorityFromRisk(alert.risk_level) >= 3)
      .sort((left, right) => dateValue(right.timestamp) - dateValue(left.timestamp))
      .slice(0, 5)
      .map((alert): ActivityItem => ({
        id: `alert:${alert.alert_id}`,
        title: priorityFromRisk(alert.risk_level) === 4 ? "Critical alert" : "High-priority alert",
        detail: shortText(alert.message || "Security activity requires review."),
        camera: alert.camera_name ?? alert.camera_id ?? undefined,
        timestamp: alert.timestamp,
      }));
  }

  return events
    .filter((event) => priorityFromEvent(event) >= 3)
    .sort((left, right) => eventTime(right) - eventTime(left))
    .slice(0, 5)
    .map((event): ActivityItem => ({
      id: `event:${event.event_id ?? event.id ?? `${event.timestamp}-${event.camera_id}`}`,
      title: priorityFromEvent(event) === 4 ? "Critical activity" : "High-priority activity",
      detail: shortText(event.explanation ?? event.description ?? event.reason ?? "Security activity requires review."),
      camera: event.camera_id,
      timestamp: event.timestamp,
    }));
}

function dashboardStatus({ availability, cameras, attentionItems }: { availability: DashboardAvailability; cameras: CameraType[]; attentionItems: AttentionItem[] }) {
  if (!Object.values(availability).every(Boolean)) return { labelKey: "degraded", tone: "degraded" as const };
  if (attentionItems.some((item) => item.priority === 4)) return { labelKey: "critical", tone: "critical" as const };
  if (attentionItems.length > 0 || cameras.length === 0) return { labelKey: "needsReview", tone: "attention" as const };
  return { labelKey: "stable", tone: "stable" as const };
}

export function OperatorDashboard({ cameras, events, alerts, incidents, evidence, status, availability, isLoading, isUnavailable, onRetry }: OperatorDashboardProps) {
  const dataAvailability = useMemo<DashboardAvailability>(() => ({
    status: availability?.status ?? !isUnavailable,
    cameras: availability?.cameras ?? !isUnavailable,
    alerts: availability?.alerts ?? !isUnavailable,
    events: availability?.events ?? !isUnavailable,
    incidents: availability?.incidents ?? !isUnavailable,
    evidence: availability?.evidence ?? !isUnavailable,
  }), [availability, isUnavailable]);
  const counts = useMemo(() => cameraCounts(cameras), [cameras]);
  const activeAlerts = useMemo(() => alerts?.filter((alert) => !alert.acknowledged), [alerts]);
  const criticalAlerts = useMemo(() => activeAlerts?.filter((alert) => priorityFromRisk(alert.risk_level) === 4), [activeAlerts]);
  const openIncidents = useMemo(() => incidents?.filter(incidentIsOpen), [incidents]);
  const attentionItems = useMemo(() => buildAttentionItems({ cameras, alerts, events, incidents, status, availability: dataAvailability }), [alerts, cameras, dataAvailability, events, incidents, status]);
  const latestActivity = useMemo(() => buildLatestActivity(alerts, events, dataAvailability.alerts), [alerts, dataAvailability.alerts, events]);
  const currentStatus = dashboardStatus({ availability: dataAvailability, cameras, attentionItems });

  if (isLoading) return <DashboardLoading />;

  return (
    <section className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8" aria-labelledby="operational-overview-title">
      <DashboardHeader status={currentStatus} />
      <MetricGrid
        activeAlerts={dataAvailability.alerts ? activeAlerts?.length : undefined}
        criticalAlerts={dataAvailability.alerts ? criticalAlerts?.length : undefined}
        openIncidents={dataAvailability.incidents ? openIncidents?.length : undefined}
        camerasOnline={dataAvailability.cameras ? counts.live : undefined}
        camerasOffline={dataAvailability.cameras ? counts.offline : undefined}
        evidenceAvailable={dataAvailability.evidence ? evidence?.length : undefined}
      />

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.82fr)]">
        <NeedsAttention items={attentionItems} unavailable={isUnavailable} onRetry={onRetry} />
        <QuickActions />
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
        <LatestCriticalActivity items={latestActivity} alertsAvailable={dataAvailability.alerts} eventsAvailable={dataAvailability.events} />
        <TodaySummary alerts={alerts} cameras={cameras} alertsAvailable={dataAvailability.alerts} camerasAvailable={dataAvailability.cameras} />
      </div>

      <SystemReadiness availability={dataAvailability} status={status} />
    </section>
  );
}

function DashboardHeader({ status }: { status: { labelKey: string; tone: "stable" | "attention" | "critical" | "degraded" } }) {
  const t = useTranslations("dashboard.header");
  const tStatus = useTranslations("dashboard.status");
  const Icon = status.tone === "stable" ? ShieldCheck : status.tone === "critical" ? ShieldAlert : status.tone === "degraded" ? WifiOff : CircleAlert;
  return <header className="flex flex-wrap items-end justify-between gap-4"><div><h1 id="operational-overview-title" className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">{t("title")}</h1><p className="mt-2 text-sm text-slate-400">{t("subtitle")}</p></div><span className={cn("inline-flex min-h-10 items-center gap-2 rounded-full border px-3.5 text-sm font-semibold", status.tone === "stable" ? "border-emerald-300/30 bg-emerald-400/10 text-emerald-100" : status.tone === "critical" ? "border-eose-300/35 bg-rose-400/10 text-rose-100" : status.tone === "attention" ? "border-amber-300/35 bg-amber-300/10 text-amber-100" : "border-slate-300/20 bg-white/[0.05] text-slate-200")}><Icon className="h-4 w-4" aria-hidden />{tStatus(status.labelKey)}</span></header>;
}

function MetricGrid({ activeAlerts, criticalAlerts, openIncidents, camerasOnline, camerasOffline, evidenceAvailable }: { activeAlerts?: number; criticalAlerts?: number; openIncidents?: number; camerasOnline?: number; camerasOffline?: number; evidenceAvailable?: number }) {
  const t = useTranslations("dashboard.metrics");
  const metrics = [
    { label: t("activeAlerts"), value: activeAlerts, icon: BellRing, tone: "warning" as const },
    { label: t("criticalAlerts"), value: criticalAlerts, icon: ShieldAlert, tone: "danger" as const },
    { label: t("openIncidents"), value: openIncidents, icon: ClipboardCheck, tone: "warning" as const },
    { label: t("camerasOnline"), value: camerasOnline, icon: Camera, tone: "good" as const },
    { label: t("camerasOffline"), value: camerasOffline, icon: CircleOff, tone: "danger" as const },
    { label: t("evidenceAvailable"), value: evidenceAvailable, icon: FileSearch, tone: "neutral" as const },
  ];
  return <section className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6" aria-label="Current security summary">{metrics.map((metric) => <MetricCard key={metric.label} {...metric} />)}</section>;
}

function MetricCard({ label, value, icon: Icon, tone }: { label: string; value?: number; icon: typeof BellRing; tone: "good" | "warning" | "danger" | "neutral" }) {
  const t = useTranslations("dashboard.metrics");
  return <article className={cn("rounded-xl border p-4", tone === "good" ? "border-emerald-300/20 bg-emerald-400/[0.045]" : tone === "warning" ? "border-amber-300/20 bg-amber-300/[0.04]" : tone === "danger" ? "border-eose-300/20 bg-rose-400/[0.04]" : "border-white/[0.1] bg-white/[0.025]")}><div className="flex items-center justify-between gap-3"><Icon className={cn("h-4.5 w-4.5", tone === "good" ? "text-emerald-200" : tone === "warning" ? "text-amber-100" : tone === "danger" ? "text-rose-200" : "text-signal-cyan")} aria-hidden /><span className="text-xs text-slate-500">{t("current")}</span></div><p className="mt-4 text-2xl font-semibold tracking-tight text-white">{typeof value === "number" ? value.toLocaleString() : t("unavailable")}</p><p className="mt-1 text-sm text-slate-400">{label}</p></article>;
}

function NeedsAttention({ items, unavailable, onRetry }: { items: AttentionItem[]; unavailable: boolean; onRetry: () => void }) {
  const t = useTranslations("dashboard.needsAttention");
  return <section className="rounded-xl border border-white/[0.1] bg-white/[0.025] p-5 sm:p-6" aria-labelledby="needs-attention-title"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-signal-cyan">{t("priorityReview")}</p><h2 id="needs-attention-title" className="mt-1 text-xl font-semibold text-white">{t("title")}</h2></div>{items.length ? <span className="rounded-full bg-amber-300/10 px-2.5 py-1 text-sm font-semibold text-amber-100">{items.length}</span> : null}</div>{unavailable && !items.length ? <div className="mt-5 rounded-lg border border-eose-300/20 bg-rose-400/[0.05] p-4"><p className="text-sm font-medium text-rose-100">{t("unavailableInfo")}</p><button type="button" onClick={onRetry} className="mt-3 min-h-9 rounded-md border border-eose-300/30 px-3 text-sm font-semibold text-rose-100 transition hover:bg-rose-400/10">{t("retry")}</button></div> : items.length ? <div className="mt-4 divide-y divide-white/[0.08]">{items.slice(0, 5).map((item) => <AttentionRow key={item.id} item={item} />)}</div> : <div className="mt-5 flex items-center gap-3 rounded-lg border border-emerald-300/20 bg-emerald-400/[0.045] p-4 text-sm text-emerald-100"><CheckCircle2 className="h-5 w-5 shrink-0" aria-hidden />{t("nothingAttention")}</div>}</section>;
}

function AttentionRow({ item }: { item: AttentionItem }) {
  const t = useTranslations("dashboard.needsAttention");
  const Icon = item.kind === "camera" ? CircleOff : item.kind === "evidence" ? FileSearch : item.kind === "incident" ? ClipboardCheck : item.kind === "detection" ? RadioTower : AlertTriangle;
  const tone = item.priority === 4 ? "text-rose-200" : item.priority >= 3 ? "text-amber-100" : "text-signal-cyan";
  return <article className="flex flex-wrap items-start gap-3 py-4 first:pt-0 last:pb-0"><span className={cn("mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/[0.1] bg-black/15", tone)}><Icon className="h-4.5 w-4.5" aria-hidden /></span><div className="min-w-0 flex-1"><p className="text-sm font-semibold text-white">{item.title}</p><p className="mt-1 text-sm text-slate-400">{item.detail}</p><p className="mt-1 text-xs text-slate-500">{[item.location, item.timestamp ? formatTimestamp(item.timestamp) : t("timeUnavailable")].filter(Boolean).join(" · ")}</p></div><Link href={item.href as any} className="inline-flex min-h-9 shrink-0 items-center rounded-md border border-signal-cyan/40 px-3 text-sm font-semibold text-signal-cyan transition hover:bg-signal-cyan/10">{t("review")}</Link></article>;
}

function QuickActions() {
  const t = useTranslations("dashboard.quickActions");
  const actions = [
    { label: t("openCameraWall"), href: "/cameras", icon: Camera },
    { label: t("reviewAlerts"), href: "/events", icon: BellRing },
    { label: t("viewIncidents"), href: "/events", icon: ClipboardCheck },
    { label: t("searchEvidence"), href: "/semantic", icon: FileSearch },
  ];
  return <section className="rounded-xl border border-white/[0.1] bg-white/[0.025] p-5 sm:p-6" aria-labelledby="quick-actions-title"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-signal-cyan">{t("operatorTools")}</p><h2 id="quick-actions-title" className="mt-1 text-xl font-semibold text-white">{t("title")}</h2><div className="mt-5 grid gap-2 sm:grid-cols-2 xl:grid-cols-1">{actions.map(({ label, href, icon: Icon }) => <Link key={label} href={href as any} className="flex min-h-12 items-center gap-3 rounded-lg border border-white/[0.1] bg-black/[0.14] px-3 text-sm font-semibold text-slate-200 transition hover:border-signal-cyan/45 hover:bg-signal-cyan/[0.055] hover:text-white"><Icon className="h-4.5 w-4.5 text-signal-cyan" aria-hidden />{label}</Link>)}</div></section>;
}

function LatestCriticalActivity({ items, alertsAvailable, eventsAvailable }: { items: ActivityItem[]; alertsAvailable: boolean; eventsAvailable: boolean }) {
  const t = useTranslations("dashboard.latestActivity");
  const canShowActivity = alertsAvailable || eventsAvailable;
  return <section className="rounded-xl border border-white/[0.1] bg-white/[0.025] p-5 sm:p-6" aria-labelledby="latest-critical-title"><div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-signal-cyan">{t("recentPriority")}</p><h2 id="latest-critical-title" className="mt-1 text-xl font-semibold text-white">{t("title")}</h2></div><Link href="/events" className="inline-flex min-h-9 items-center gap-1 text-sm font-semibold text-signal-cyan transition hover:text-cyan-200">{t("viewAll")}</Link></div>{!canShowActivity ? <p className="mt-5 text-sm text-slate-400">{t("unavailable")}</p> : items.length ? <div className="mt-4 divide-y divide-white/[0.08]">{items.map((item) => <article key={item.id} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0"><ShieldAlert className="mt-0.5 h-4.5 w-4.5 shrink-0 text-rose-200" aria-hidden /><div className="min-w-0 flex-1"><p className="text-sm font-semibold text-white">{item.title}</p>{item.detail ? <p className="mt-1 text-sm text-slate-400">{item.detail}</p> : null}<p className="mt-1 text-xs text-slate-500">{[item.camera, item.timestamp ? formatTimestamp(item.timestamp) : "Time unavailable"].filter(Boolean).join(" · ")}</p></div></article>)}</div> : <p className="mt-5 text-sm text-slate-400">{t("noHighPriority")}</p>}</section>;
}

function TodaySummary({ alerts, cameras, alertsAvailable, camerasAvailable }: { alerts?: OperationalAlert[]; cameras: CameraType[]; alertsAvailable: boolean; camerasAvailable: boolean }) {
  const t = useTranslations("dashboard.todaySummary");
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const todayAlerts = alertsAvailable && alerts ? alerts.filter((alert) => dateValue(alert.timestamp) >= startOfToday.getTime()) : undefined;
  const highestAlert = todayAlerts?.slice().sort((left, right) => priorityFromRisk(right.risk_level) - priorityFromRisk(left.risk_level) || dateValue(right.timestamp) - dateValue(left.timestamp))[0];
  const highestCamera = highestAlert ? cameraName(cameras.find((camera) => camera.camera_id === highestAlert.camera_id), highestAlert.camera_name ?? highestAlert.camera_id) : undefined;
  const cards = [
    { label: t("alertsToday"), value: todayAlerts?.length },
    { label: t("resolved"), value: undefined as number | undefined },
    { label: t("stillOpen"), value: todayAlerts?.filter((alert) => !alert.acknowledged).length },
  ];
  return <section className="rounded-xl border border-white/[0.1] bg-white/[0.025] p-5 sm:p-6" aria-labelledby="today-summary-title"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-signal-cyan">{t("today")}</p><h2 id="today-summary-title" className="mt-1 text-xl font-semibold text-white">{t("title")}</h2><div className="mt-5 grid gap-3 sm:grid-cols-3">{cards.map((card) => <div key={card.label} className="rounded-lg border border-white/[0.08] bg-black/[0.14] p-3"><p className="text-xs text-slate-500">{card.label}</p><p className="mt-2 text-xl font-semibold text-white">{typeof card.value === "number" ? card.value.toLocaleString() : t("unavailable")}</p></div>)}</div><div className="mt-4 rounded-lg border border-white/[0.08] bg-black/[0.14] p-3"><p className="text-xs text-slate-500">{t("highestRisk")}</p><p className="mt-2 text-sm font-semibold text-white">{alertsAvailable && camerasAvailable ? highestCamera ?? t("unavailable") : t("unavailable")}</p></div><p className="mt-3 text-xs leading-5 text-slate-500">{t("resolvedNotAvailable")}</p></section>;
}

function SystemReadiness({ availability, status }: { availability: DashboardAvailability; status?: StatusResponse }) {
  const t = useTranslations("dashboard.systemReadiness");
  const system = getStatusSystem(status);
  const rows = [
    { label: t("liveUpdates"), value: availability.events ? t("ready") : t("unavailable"), tone: availability.events ? "good" : "muted" },
    { label: t("detection"), value: !availability.status ? t("unavailable") : system.running === true ? t("ready") : system.running === false ? t("needsAttention") : t("unavailable"), tone: system.running === true && availability.status ? "good" : system.running === false && availability.status ? "warning" : "muted" },
    { label: t("evidence"), value: availability.evidence ? t("ready") : t("unavailable"), tone: availability.evidence ? "good" : "muted" },
    { label: t("storage"), value: availability.evidence ? t("available") : t("unavailable"), tone: availability.evidence ? "good" : "muted" },
    { label: t("agent"), value: t("unavailable"), tone: "muted" },
  ];
  return <section className="mt-5 rounded-xl border border-white/[0.1] bg-white/[0.025] p-5 sm:p-6" aria-labelledby="system-readiness-title"><div className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-signal-cyan">{t("currentCapability")}</p><h2 id="system-readiness-title" className="mt-1 text-xl font-semibold text-white">{t("title")}</h2></div><Sparkles className="h-5 w-5 text-signal-cyan" aria-hidden /></div><div className="mt-5 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">{rows.map((row) => <div key={row.label} className="flex items-center justify-between gap-3 rounded-lg border border-white/[0.08] bg-black/[0.14] px-3 py-3"><span className="text-sm text-slate-300">{row.label}</span><span className={cn("inline-flex items-center gap-1.5 text-xs font-semibold", row.tone === "good" ? "text-emerald-200" : row.tone === "warning" ? "text-amber-100" : "text-slate-400")}><span className={cn("h-2 w-2 rounded-full", row.tone === "good" ? "bg-emerald-400" : row.tone === "warning" ? "bg-amber-300" : "bg-slate-500")} />{row.value}</span></div>)}</div></section>;
}

function DashboardLoading() {
  return <section className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8" aria-busy="true" aria-label="Loading operational overview"><div className="h-10 w-64 animate-pulse rounded bg-white/[0.07]" /><div className="mt-3 h-5 w-96 max-w-full animate-pulse rounded bg-white/[0.04]" /><div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">{Array.from({ length: 6 }).map((_, index) => <div key={index} className="h-32 animate-pulse rounded-xl border border-white/[0.1] bg-white/[0.025]" />)}</div><div className="mt-5 grid gap-5 xl:grid-cols-2"><div className="h-80 animate-pulse rounded-xl border border-white/[0.1] bg-white/[0.025]" /><div className="h-64 animate-pulse rounded-xl border border-white/[0.1] bg-white/[0.025]" /></div></section>;
}

export const operatorDashboardInternals = { buildAttentionItems, cameraCondition, cameraCounts, cameraName, priorityFromEvent, priorityFromRisk };
