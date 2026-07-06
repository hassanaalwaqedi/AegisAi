"use client";

import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Bell,
  Binary,
  Building2,
  Calendar,
  Camera,
  Car,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleDot,
  Cctv,
  Crosshair,
  Eye,
  FileText,
  Gauge,
  GraduationCap,
  Landmark,
  Lock,
  MapPin,
  Monitor,
  Network,
  Plus,
  RadioTower,
  ScanSearch,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Siren,
  SlidersHorizontal,
  Users,
  Video,
  Workflow,
  XCircle
} from "lucide-react";
import { RiskBadge } from "@/components/dashboard/risk-badge";
import { Badge } from "@/components/ui/badge";
import { appConfig } from "@/lib/config";
import { formatDecimal, formatNumber, formatPercent, formatTimestamp, getStatusSystem } from "@/lib/data-format";
import { cn, formatTime } from "@/lib/utils";
import { useCamerasQuery, useEventsQuery, useStatisticsQuery, useStatusQuery, useTracksQuery } from "@/hooks/use-aegis-api";
import type { Camera as CameraType, RiskEvent, RiskLevel, StatusSystem, Track } from "@/types";

const sideNav = [
  { href: "/", label: "Overview", icon: ShieldCheck },
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/cameras", label: "Cameras", icon: Cctv },
  { href: "/events", label: "Events", icon: RadioTower },
  { href: "/tracks", label: "Tracks", icon: Binary },
  { href: "/analytics", label: "Analytics", icon: Activity },
  { href: "/semantic", label: "Semantic", icon: ScanSearch }
];

const topNav = [
  { href: "/", label: "Overview" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/cameras", label: "Cameras" },
  { href: "/events", label: "Events" },
  { href: "/tracks", label: "Tracks" },
  { href: "/analytics", label: "Analytics" },
  { href: "/semantic", label: "Semantic" }
];

const vehicleClasses = ["car", "truck", "bus", "motorcycle", "bicycle"];
const weaponClasses = new Set(["knife", "pistol", "gun", "weapon"]);
const riskRank: Record<RiskLevel, number> = {
  LOW: 0,
  CANDIDATE_MEDIUM: 1,
  MEDIUM: 2,
  HIGH: 3,
  CRITICAL: 4
};

const pipeline = [
  { label: "Camera Source", icon: Video },
  { label: "AI Detection", icon: ScanSearch },
  { label: "Tracking", icon: Crosshair },
  { label: "Behavior Analysis", icon: Activity },
  { label: "Weapon Detection", icon: ShieldAlert },
  { label: "Risk Fusion", icon: Gauge },
  { label: "Evidence Alert", icon: Bell },
  { label: "Operator Dashboard", icon: Monitor }
];

const securityValues = [
  { icon: Eye, title: "Reduce Manual Monitoring", body: "Focus teams on real tracks and backend events." },
  { icon: Siren, title: "Surface High-Risk Events Faster", body: "Prioritize confirmed risk and candidate signals." },
  { icon: FileText, title: "Keep Evidence for Review", body: "Preserve model source, reasons, and confidence." },
  { icon: Gauge, title: "Prioritize What Matters Most", body: "Show current risk from live backend fields." },
  { icon: Network, title: "Scale Multi-Camera Operations", body: "Operate registered real camera sources." }
];

const useCases = [
  { icon: Building2, title: "Smart cities", body: "Public spaces, intersections, municipal operations." },
  { icon: GraduationCap, title: "Schools and campuses", body: "Campus security with camera-level evidence." },
  { icon: Landmark, title: "Critical infrastructure", body: "Utilities, transport hubs, and protected sites." },
  { icon: RadioTower, title: "Public events", body: "Crowd, track, and incident visibility." },
  { icon: ShieldCheck, title: "Private facilities", body: "Offices, hospitals, warehouses, retail." },
  { icon: Lock, title: "Border and gate monitoring", body: "Entrances, checkpoints, and vehicle movement." }
];

export default function LandingPage() {
  const statusQuery = useStatusQuery();
  const statisticsQuery = useStatisticsQuery();
  const tracksQuery = useTracksQuery();
  const eventsQuery = useEventsQuery();
  const camerasQuery = useCamerasQuery();

  const system = getStatusSystem(statusQuery.data);
  const cameras = camerasQuery.data?.cameras ?? [];
  const tracks = tracksQuery.data?.tracks ?? [];
  const events = eventsQuery.data?.events ?? [];
  const supportedClasses = normalizeClasses(system.supported_classes);
  const activeCameras = cameras.filter((camera) => camera.runtime.running || camera.runtime.status === "online").length;
  const currentRisk = getCurrentRisk(system, tracks, events, statisticsQuery.data?.risk?.max_level) ?? "LOW";
  const weaponSupported = system.weapon_detection_supported === true;
  const weaponTracks = tracks.filter((track) => isWeaponTrack(track));
  const recentEvents = events.filter((event) => isWithinHours(event.timestamp, 24));
  const latestCamera = latestCameraFrom(cameras);
  const latestTrack = latestTrackFrom(tracks);
  const latestEvent = latestEventFrom(events);

  return (
    <div className="min-h-screen bg-command-950 text-slate-100">
      <div className="flex min-h-screen">
        <aside className="hidden w-[260px] shrink-0 border-r border-white/10 bg-command-950/96 lg:flex lg:flex-col">
          <div className="border-b border-white/10 p-5">
            <Link href="/" className="flex items-center gap-3">
              <span className="flex h-12 w-12 items-center justify-center rounded-lg border border-signal-cyan/35 bg-signal-cyan/10 text-signal-cyan">
                <ShieldCheck className="h-6 w-6" aria-hidden />
              </span>
              <span>
                <span className="block text-lg font-semibold text-white">AegisAI</span>
                <span className="block text-xs text-slate-400">Risk Intelligence Platform</span>
              </span>
            </Link>
          </div>

          <nav className="flex-1 space-y-1 p-4">
            {sideNav.map((item) => (
              <SideNavItem key={item.href} {...item} active={item.href === "/"} />
            ))}
          </nav>

          <div className="space-y-4 p-4">
            <div className="rounded-lg border border-white/10 bg-white/[0.035] p-3">
              <p className="text-xs uppercase tracking-[0.14em] text-slate-500">Quick actions</p>
              <div className="mt-3 grid gap-2">
                <QuickAction href="/cameras" icon={Plus} label="Add Camera" />
                <QuickAction href="/events" icon={Calendar} label="View Events" />
                <QuickAction href="/dashboard" icon={Activity} label="System Health" />
              </div>
            </div>
            <RiskMiniCard risk={currentRisk} events={events} />
          </div>
        </aside>

        <main className="min-w-0 flex-1">
          <header className="sticky top-0 z-40 border-b border-white/10 bg-command-950/88 backdrop-blur-xl">
            <div className="flex min-h-[72px] items-center justify-between gap-4 px-4 sm:px-6 xl:px-8">
              <div className="flex items-center gap-3 lg:hidden">
                <span className="flex h-10 w-10 items-center justify-center rounded-md border border-signal-cyan/35 bg-signal-cyan/10 text-signal-cyan">
                  <ShieldCheck className="h-5 w-5" aria-hidden />
                </span>
                <span className="font-semibold text-white">AegisAI</span>
              </div>
              <nav className="hidden max-w-full gap-2 overflow-x-auto md:flex">
                {topNav.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "inline-flex min-h-10 shrink-0 items-center rounded-md px-4 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white",
                      item.href === "/" && "border border-white/10 bg-white/10 text-signal-cyan"
                    )}
                  >
                    {item.label}
                  </Link>
                ))}
              </nav>
              <div className="flex items-center gap-3">
                <span className="relative hidden h-9 w-9 items-center justify-center rounded-md border border-white/10 bg-white/[0.04] text-slate-300 sm:flex">
                  <Bell className="h-4 w-4" aria-hidden />
                  {events.length > 0 ? (
                    <span className="absolute -right-1 -top-1 rounded-full bg-signal-red px-1.5 text-[10px] font-semibold text-white">
                      {Math.min(events.length, 99)}
                    </span>
                  ) : null}
                </span>
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-sm font-semibold text-slate-200">H</span>
                <span className="hidden items-center gap-2 text-sm text-slate-300 sm:flex">
                  Admin
                  <ChevronDown className="h-4 w-4" aria-hidden />
                </span>
              </div>
            </div>
          </header>

          <section className="mx-auto w-full max-w-[1780px] px-4 py-7 sm:px-6 xl:px-8">
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(420px,0.55fr)_210px] xl:items-center">
              <div>
                <h1 className="text-3xl font-semibold tracking-normal text-white lg:text-4xl">
                  AegisAI - Real-Time Risk Intelligence
                </h1>
                <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">
                  Transforming live video into actionable intelligence. Detect. Track. Analyze. Alert.
                </p>
              </div>
              <SystemStrip system={system} statusOk={statusQuery.isSuccess} />
              <Link
                href="/dashboard"
                className="inline-flex min-h-12 items-center justify-center gap-3 rounded-md bg-blue-600 px-4 text-sm font-semibold text-white shadow-[0_0_30px_rgba(37,99,235,0.25)] transition hover:bg-blue-500"
              >
                Open Live Dashboard
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Link>
            </div>

            {statusQuery.isError ? (
              <div className="mt-5 rounded-lg border border-rose-400/25 bg-rose-500/[0.06] p-4 text-sm text-rose-100">
                Backend status unavailable: {String(statusQuery.error instanceof Error ? statusQuery.error.message : "request failed")}
              </div>
            ) : null}

            <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
              <MetricCard icon={Cctv} label="Active Cameras" value={`${formatNumber(activeCameras)} / ${formatNumber(cameras.length)}`} detail="Online" tone="cyan" />
              <MetricCard icon={Activity} label="Frames Processed" value={formatMetric(system.frames_processed)} detail="Backend reported" tone="cyan" />
              <MetricCard icon={Crosshair} label="Active Tracks" value={formatMetric(tracksQuery.data?.count ?? system.active_tracks)} detail="Currently" tone="green" />
              <MetricCard icon={Bell} label="Events (24h)" value={formatNumber(recentEvents.length)} detail="Real events" tone="red" />
              <MetricCard icon={ShieldAlert} label="Weapon Detections" value={formatNumber(weaponTracks.length)} detail={weaponSupported ? "Current tracks" : "Not enabled"} tone="red" />
              <MetricCard icon={Gauge} label="Risk Level" value={<RiskBadge level={currentRisk} />} detail="Current" tone={riskTone(currentRisk)} />
            </div>

            <div className="mt-4 grid gap-4 2xl:grid-cols-[0.78fr_1.22fr]">
              <Panel title="What AegisAI Detects">
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  <DetectCard icon={Users} title="People" status={supportedClasses.has("person") ? "Supported" : "Not reported"} model={system.model_name} confidence="Backend confidence" tone="cyan" />
                  <DetectCard icon={Car} title="Vehicles" status={hasVehicleSupport(supportedClasses) ? "Supported" : "Not reported"} model={system.model_name} confidence="Backend confidence" tone="green" />
                  <DetectCard icon={Users} title="Crowd Density" status="Candidate" model="Tracking / statistics" confidence="Rule-based" tone="violet" />
                  <DetectCard icon={MapPin} title="Restricted Zone" status="Candidate" model="Risk engine" confidence="Needs zone evidence" tone="amber" />
                  <DetectCard icon={Activity} title="Suspicious Motion" status="Candidate" model="BBox motion rules" confidence="Needs confirmation" tone="amber" />
                  <DetectCard
                    icon={ShieldAlert}
                    title="Knife / Pistol"
                    status={weaponSupported ? "Supported" : "Not enabled"}
                    model={weaponModelSource(system)}
                    confidence={weaponSupported ? "Backend confidence" : "Unavailable"}
                    tone="red"
                    flag={weaponSupported ? "LIVE" : undefined}
                  />
                </div>
              </Panel>

              <Panel
                title="Live Camera Overview"
                action={
                  <Link href="/cameras" className="inline-flex items-center gap-1 text-xs font-medium text-signal-cyan hover:text-cyan-200">
                    View All Cameras
                    <ChevronRight className="h-3.5 w-3.5" aria-hidden />
                  </Link>
                }
              >
                {cameras.length === 0 ? (
                  <HonestEmpty title="No cameras registered yet." description="Add a camera source to show real live previews here." />
                ) : (
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {cameras.slice(0, 6).map((camera) => (
                      <CameraTile key={camera.camera_id} camera={camera} tracks={tracks.filter((track) => trackCameraId(track) === camera.camera_id)} />
                    ))}
                  </div>
                )}
              </Panel>
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-[1.25fr_0.75fr_0.82fr]">
              <Panel title="Security Value">
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                  {securityValues.map((item) => (
                    <ValueCard key={item.title} {...item} />
                  ))}
                </div>
              </Panel>

              <Panel title="Recent Activity">
                <RecentActivity events={events} latestCamera={latestCamera} latestTrack={latestTrack} latestEvent={latestEvent} />
              </Panel>

              <Panel title="System Capability">
                <CapabilityList system={system} supportedClasses={supportedClasses} />
              </Panel>
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_0.42fr]">
              <Panel title="AI Pipeline">
                <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-8">
                  {pipeline.map((item, index) => (
                    <PipelineStep key={item.label} {...item} isLast={index === pipeline.length - 1} />
                  ))}
                </div>
              </Panel>

              <Panel title="About AegisAI">
                <div className="grid gap-4 sm:grid-cols-[1fr_150px] sm:items-center">
                  <div className="space-y-3 text-sm leading-7 text-slate-400">
                    <p>AegisAI turns live video into real-time risk intelligence.</p>
                    <p>Built for smart cities, schools, public events, and critical infrastructure.</p>
                    <p>Every status and event shown here is grounded in backend data.</p>
                  </div>
                  <div className="flex aspect-square items-center justify-center rounded-2xl border border-signal-cyan/20 bg-signal-cyan/[0.06] text-signal-cyan">
                    <ShieldCheck className="h-20 w-20" aria-hidden />
                  </div>
                </div>
              </Panel>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-6">
              {useCases.map((item) => (
                <UseCaseMini key={item.title} {...item} />
              ))}
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

function SideNavItem({
  href,
  label,
  icon: Icon,
  active
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  active?: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white",
        active && "bg-blue-500/18 text-white"
      )}
    >
      <Icon className={cn("h-4 w-4", active ? "text-signal-cyan" : "text-slate-400")} aria-hidden />
      {label}
    </Link>
  );
}

function QuickAction({ href, icon: Icon, label }: { href: string; icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>; label: string }) {
  return (
    <Link href={href} className="flex min-h-9 items-center gap-3 rounded-md border border-white/8 bg-white/[0.045] px-3 text-sm text-slate-200 transition hover:bg-white/10">
      <Icon className="h-4 w-4 text-signal-cyan" aria-hidden />
      {label}
    </Link>
  );
}

function RiskMiniCard({ risk, events }: { risk: RiskLevel; events: RiskEvent[] }) {
  const scores = events.slice(0, 12).map((event) => event.risk_score ?? 0).filter((value) => Number.isFinite(value));
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
      <div className="flex items-center gap-3">
        <ShieldAlert className="h-5 w-5 text-signal-red" aria-hidden />
        <span className="text-sm text-slate-300">Risk Level (Live)</span>
      </div>
      <div className="mt-3">
        <RiskBadge level={risk} />
      </div>
      <p className="mt-2 text-xs text-slate-400">
        {events.length ? `${events.length} backend events returned` : "No backend events yet"}
      </p>
      {scores.length ? (
        <div className="mt-4 flex h-9 items-end gap-1">
          {scores.map((score, index) => (
            <span key={`${score}-${index}`} className="flex-1 rounded-sm bg-signal-red/80" style={{ height: `${Math.max(10, Math.min(100, score * 100))}%` }} />
          ))}
        </div>
      ) : (
        <div className="mt-4 rounded-md border border-white/8 bg-black/20 p-2 text-xs text-slate-500">No risk trend data.</div>
      )}
    </div>
  );
}

function SystemStrip({ system, statusOk }: { system: StatusSystem; statusOk: boolean }) {
  return (
    <div className="grid gap-3 rounded-lg border border-white/10 bg-white/[0.045] p-4 sm:grid-cols-4">
      <StripItem label="System Status" value={statusOk ? "Operational" : "Unavailable"} good={statusOk} />
      <StripItem label="Backend" value={statusOk ? "Connected" : "Not connected"} good={statusOk} />
      <StripItem label="Uptime" value={formatUptime(system.uptime_seconds)} />
      <StripItem label="Version" value={String((system as StatusSystem & { version?: string }).version ?? "Not reported")} />
    </div>
  );
}

function StripItem({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="border-white/10 sm:border-l sm:first:border-l-0 sm:pl-5 sm:first:pl-0">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 flex items-center gap-2 text-sm font-medium text-white">
        {good !== undefined ? <span className={cn("h-2 w-2 rounded-full", good ? "bg-emerald-400" : "bg-rose-400")} /> : null}
        {value}
      </p>
    </div>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  tone
}: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  label: string;
  value: React.ReactNode;
  detail: string;
  tone: "cyan" | "green" | "red" | "amber" | "neutral";
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.045] p-4 shadow-glow">
      <div className="flex items-center gap-3">
        <span className={cn("flex h-11 w-11 items-center justify-center rounded-full border", toneClasses(tone))}>
          <Icon className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm text-slate-400">{label}</p>
          <div className="mt-1 text-2xl font-semibold text-white">{value}</div>
          <p className="text-xs text-slate-500">{detail}</p>
        </div>
      </div>
    </div>
  );
}

function Panel({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.04] p-4 shadow-glow">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-white">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function DetectCard({
  icon: Icon,
  title,
  status,
  model,
  confidence,
  tone,
  flag
}: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  title: string;
  status: string;
  model?: string;
  confidence: string;
  tone: "cyan" | "green" | "violet" | "amber" | "red";
  flag?: string;
}) {
  return (
    <div className="relative rounded-lg border border-white/10 bg-black/20 p-4">
      {flag ? <span className="absolute right-3 top-3 rounded bg-emerald-400/20 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-200">{flag}</span> : null}
      <div className="flex items-center gap-3">
        <Icon className={cn("h-7 w-7", iconTone(tone))} aria-hidden />
        <div>
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          <p className={cn("mt-1 text-xs font-medium", status === "Supported" ? "text-emerald-300" : status === "Candidate" ? "text-amber-200" : "text-slate-400")}>{status}</p>
        </div>
      </div>
      <div className="mt-4 space-y-1 text-xs text-slate-400">
        <p>Model: {model || "Not reported"}</p>
        <p>Confidence: {confidence}</p>
      </div>
    </div>
  );
}

function CameraTile({ camera, tracks }: { camera: CameraType; tracks: Track[] }) {
  const hasFrame = Boolean(camera.runtime.last_frame_time || camera.runtime.width || camera.runtime.frames_received);
  const drawable = tracks.filter((track) => track.bbox).slice(0, 4);
  return (
    <Link href="/cameras" className="group overflow-hidden rounded-lg border border-white/10 bg-black/25 transition hover:border-signal-cyan/35">
      <div className="relative aspect-video bg-command-900">
        {hasFrame ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`${appConfig.apiUrl}/cameras/${encodeURIComponent(camera.camera_id)}/snapshot`}
            alt={`${camera.camera_id} snapshot`}
            className="h-full w-full object-cover opacity-85"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-slate-500">
            <Camera className="h-6 w-6" aria-hidden />
            <span className="text-xs">No live frame yet</span>
          </div>
        )}
        <div className="absolute left-2 top-2 flex items-center gap-2 rounded bg-command-950/80 px-2 py-1 text-xs text-white">
          <span className={cn("h-2 w-2 rounded-full", camera.runtime.status === "online" ? "bg-emerald-400" : "bg-slate-500")} />
          <span className="max-w-[150px] truncate">{camera.name || camera.camera_id}</span>
        </div>
        {camera.runtime.running ? (
          <div className="absolute right-2 top-2 flex items-center gap-1 rounded bg-command-950/80 px-2 py-1 text-xs text-rose-100">
            <span className="h-2 w-2 rounded-full bg-rose-400" />
            REC
          </div>
        ) : null}
        {drawable.map((track) => (
          <MiniBox key={String(track.track_id)} track={track} camera={camera} />
        ))}
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-white/10 px-3 py-2 text-xs text-slate-400">
        <span>{sourceLabel(camera.source_type)}</span>
        <span>{formatDecimal(camera.runtime.fps, 1, "0.0")} FPS</span>
      </div>
    </Link>
  );
}

function MiniBox({ track, camera }: { track: Track; camera: CameraType }) {
  if (!track.bbox || !camera.runtime.width || !camera.runtime.height) return null;
  const [x1, y1, x2, y2] = track.bbox;
  const left = `${(x1 / camera.runtime.width) * 100}%`;
  const top = `${(y1 / camera.runtime.height) * 100}%`;
  const width = `${Math.max(3, ((x2 - x1) / camera.runtime.width) * 100)}%`;
  const height = `${Math.max(4, ((y2 - y1) / camera.runtime.height) * 100)}%`;
  const weapon = isWeaponTrack(track);
  return (
    <span
      className={cn("absolute rounded-sm border", weapon ? "border-signal-red shadow-alert" : "border-blue-400")}
      style={{ left, top, width, height }}
    >
      <span className={cn("absolute -top-5 left-0 whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-medium text-white", weapon ? "bg-signal-red" : "bg-blue-600")}>
        {String(track.class_name ?? "object").toLowerCase()} {formatPercent(track.confidence, "")}
      </span>
    </span>
  );
}

function ValueCard({ icon: Icon, title, body }: { icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>; title: string; body: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-4">
      <Icon className="h-6 w-6 text-signal-cyan" aria-hidden />
      <h3 className="mt-4 text-sm font-semibold text-white">{title}</h3>
      <p className="mt-2 text-xs leading-5 text-slate-400">{body}</p>
    </div>
  );
}

function RecentActivity({
  events,
  latestCamera,
  latestTrack,
  latestEvent
}: {
  events: RiskEvent[];
  latestCamera?: CameraType;
  latestTrack?: Track;
  latestEvent?: RiskEvent;
}) {
  const rows = events.slice(0, 5);
  if (!rows.length && !latestCamera && !latestTrack && !latestEvent) {
    return <HonestEmpty title="No live activity detected yet." description="Start a camera source to populate this section." />;
  }

  if (!rows.length) {
    return (
      <div className="space-y-3">
        <ActivityRow icon={Camera} title="Latest camera" value={latestCamera?.camera_id ?? "Not reported"} detail={latestCamera?.runtime.status ?? "No status"} />
        <ActivityRow icon={Crosshair} title="Latest track" value={latestTrack?.class_name ?? "Not reported"} detail={latestTrack ? `Track ${String(latestTrack.track_id)}` : "No track"} />
        <ActivityRow icon={Bell} title="Latest event" value={latestEvent ? eventTitle(latestEvent) : "Not reported"} detail={latestEvent ? formatTimestamp(latestEvent.timestamp) : "No event"} />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {rows.map((event, index) => (
        <ActivityRow
          key={eventKey(event, index)}
          icon={eventIcon(event)}
          title={eventTitle(event)}
          value={String(event.object_class ?? event.object_type ?? event.class_name ?? event.risk_level ?? "event")}
          detail={formatTimestamp(event.timestamp)}
          score={event.risk_score}
        />
      ))}
    </div>
  );
}

function ActivityRow({
  icon: Icon,
  title,
  value,
  detail,
  score
}: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  title: string;
  value: string;
  detail: string;
  score?: number;
}) {
  return (
    <div className="grid grid-cols-[22px_minmax(0,1fr)_auto] items-center gap-3 rounded-md border border-white/8 bg-black/20 p-2.5">
      <Icon className="h-4 w-4 text-signal-cyan" aria-hidden />
      <div className="min-w-0">
        <p className="truncate text-sm text-white">{title}</p>
        <p className="truncate text-xs text-slate-500">{value}</p>
      </div>
      <div className="text-right">
        {score !== undefined ? <p className="text-xs font-semibold text-amber-200">{formatDecimal(score, 2)}</p> : null}
        <p className="text-xs text-slate-500">{detail}</p>
      </div>
    </div>
  );
}

function CapabilityList({ system, supportedClasses }: { system: StatusSystem; supportedClasses: Set<string> }) {
  const rows = [
    { label: "Person / Vehicle Detection", enabled: supportedClasses.has("person") || hasVehicleSupport(supportedClasses), icon: Users },
    { label: "Weapon Detection", enabled: system.weapon_detection_supported === true, icon: ShieldAlert },
    { label: "Action Recognition", enabled: system.action_recognition_supported === true, icon: Activity },
    { label: "Pose Estimation", enabled: system.pose_estimation_supported === true, icon: SlidersHorizontal },
    { label: "Semantic Verification", enabled: system.semantic_verification_supported === true, icon: ScanSearch }
  ];
  return (
    <div className="space-y-2">
      {rows.map((row) => {
        const Icon = row.icon;
        return (
          <div key={row.label} className="flex items-center justify-between gap-3 rounded-md border border-white/8 bg-black/20 p-3">
            <div className="flex items-center gap-3">
              <Icon className={cn("h-4 w-4", row.enabled ? "text-emerald-300" : "text-slate-500")} aria-hidden />
              <span className="text-sm text-slate-200">{row.label}</span>
            </div>
            <span className={cn("text-xs", row.enabled ? "text-emerald-300" : "text-slate-500")}>{row.enabled ? "Enabled" : "Not Enabled"}</span>
          </div>
        );
      })}
    </div>
  );
}

function PipelineStep({
  label,
  icon: Icon,
  isLast
}: {
  label: string;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  isLast?: boolean;
}) {
  return (
    <div className="relative rounded-lg border border-white/10 bg-black/20 p-3 text-center">
      <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-lg border border-signal-cyan/25 bg-signal-cyan/10 text-signal-cyan">
        <Icon className="h-6 w-6" aria-hidden />
      </span>
      <p className="mt-3 text-xs font-medium text-white">{label}</p>
      {!isLast ? <ArrowRight className="absolute -right-3 top-8 hidden h-4 w-4 text-slate-500 xl:block" aria-hidden /> : null}
    </div>
  );
}

function UseCaseMini({ icon: Icon, title, body }: { icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>; title: string; body: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
      <Icon className="h-5 w-5 text-signal-teal" aria-hidden />
      <h3 className="mt-3 text-sm font-semibold text-white">{title}</h3>
      <p className="mt-1 text-xs leading-5 text-slate-400">{body}</p>
    </div>
  );
}

function HonestEmpty({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center rounded-lg border border-dashed border-white/10 bg-black/20 p-6 text-center">
      <Circle className="h-6 w-6 text-slate-600" aria-hidden />
      <p className="mt-3 text-sm font-semibold text-white">{title}</p>
      <p className="mt-2 text-sm text-slate-500">{description}</p>
    </div>
  );
}

function formatMetric(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
    if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
    return formatNumber(value);
  }
  return "Not reported";
}

function formatUptime(seconds?: number) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) return "Not reported";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function normalizeClasses(values?: string[]) {
  return new Set((values ?? []).map((value) => value.toLowerCase()));
}

function hasVehicleSupport(classes: Set<string>) {
  return vehicleClasses.some((className) => classes.has(className));
}

function weaponModelSource(system: StatusSystem) {
  const record = system as StatusSystem & { weapon_detector?: { model_name?: string } };
  return record.weapon_detector?.model_name ?? (system.weapon_detection_supported ? "Backend weapon detector" : "Not enabled");
}

function getCurrentRisk(system: StatusSystem, tracks?: Track[], events?: RiskEvent[], statisticsRisk?: RiskLevel) {
  const candidates = [
    system.max_risk_level,
    statisticsRisk,
    ...(tracks ?? []).map((track) => track.risk_level),
    ...(events ?? []).map((event) => event.risk_level)
  ].filter((value): value is RiskLevel => Boolean(value && riskRank[value as RiskLevel] !== undefined));

  return candidates.reduce<RiskLevel | undefined>((current, value) => {
    if (!current) return value;
    return riskRank[value] > riskRank[current] ? value : current;
  }, undefined);
}

function latestCameraFrom(cameras?: CameraType[]) {
  return cameras?.slice().sort((a, b) => Date.parse(b.runtime.last_frame_time ?? b.updated_at ?? "") - Date.parse(a.runtime.last_frame_time ?? a.updated_at ?? ""))[0];
}

function latestTrackFrom(tracks?: Track[]) {
  return tracks?.slice().sort((a, b) => Date.parse(String(b.last_seen ?? b.last_updated ?? "")) - Date.parse(String(a.last_seen ?? a.last_updated ?? "")))[0];
}

function latestEventFrom(events?: RiskEvent[]) {
  return events?.slice().sort((a, b) => eventTime(b) - eventTime(a))[0];
}

function eventTime(event: RiskEvent) {
  if (typeof event.timestamp === "number") return event.timestamp * 1000;
  if (typeof event.timestamp === "string") return Date.parse(event.timestamp) || 0;
  return 0;
}

function isWithinHours(timestamp: RiskEvent["timestamp"], hours: number) {
  const raw = typeof timestamp === "number" ? timestamp * 1000 : typeof timestamp === "string" ? Date.parse(timestamp) : 0;
  if (!raw) return false;
  return Date.now() - raw <= hours * 3600 * 1000;
}

function eventTitle(event: RiskEvent) {
  return event.title ?? event.description ?? event.reason ?? event.explanation ?? "Backend event";
}

function eventKey(event: RiskEvent, index: number) {
  return String(event.event_id ?? event.id ?? `${event.timestamp ?? "event"}-${event.track_id ?? index}`);
}

function eventIcon(event: RiskEvent) {
  const objectClass = String(event.object_class ?? event.object_type ?? event.class_name ?? "").toLowerCase();
  if (weaponClasses.has(objectClass)) return ShieldAlert;
  if (event.risk_level === "CRITICAL" || event.risk_level === "HIGH") return AlertTriangle;
  return Activity;
}

function trackCameraId(track: Track) {
  const record = track as Track & { camera_id?: string };
  if (record.camera_id) return record.camera_id;
  const trackId = String(track.track_id ?? "");
  return trackId.includes(":") ? trackId.split(":")[0] : "";
}

function isWeaponTrack(track: Track) {
  const className = String(track.class_name ?? "").toLowerCase();
  return Boolean(track.is_weapon || weaponClasses.has(className));
}

function sourceLabel(source: CameraType["source_type"]) {
  const labels: Record<CameraType["source_type"], string> = {
    LOCAL_DEVICE: "Local",
    RTSP_STREAM: "RTSP",
    HTTP_STREAM: "HTTP",
    BROWSER_WEBCAM: "Browser",
    UPLOADED_VIDEO: "Video"
  };
  return labels[source];
}

function toneClasses(tone: "cyan" | "green" | "red" | "amber" | "neutral") {
  if (tone === "green") return "border-emerald-300/25 bg-emerald-300/10 text-emerald-300";
  if (tone === "red") return "border-signal-red/25 bg-signal-red/10 text-signal-red";
  if (tone === "amber") return "border-amber-300/25 bg-amber-300/10 text-amber-200";
  if (tone === "neutral") return "border-slate-400/20 bg-slate-400/10 text-slate-300";
  return "border-signal-cyan/25 bg-signal-cyan/10 text-signal-cyan";
}

function iconTone(tone: "cyan" | "green" | "violet" | "amber" | "red") {
  if (tone === "green") return "text-emerald-300";
  if (tone === "violet") return "text-signal-violet";
  if (tone === "amber") return "text-amber-300";
  if (tone === "red") return "text-signal-red";
  return "text-signal-cyan";
}

function riskTone(risk: RiskLevel) {
  if (risk === "CRITICAL" || risk === "HIGH") return "red";
  if (risk === "MEDIUM" || risk === "CANDIDATE_MEDIUM") return "amber";
  return "green";
}
