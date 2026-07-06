import { AlertTriangle, Database, Loader2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { getErrorCode, getErrorMessage } from "@/lib/errors";

export function LoadingState({ label = "Loading backend data" }: { label?: string }) {
  return (
    <Card className="flex min-h-40 items-center justify-center gap-3 text-slate-300">
      <Loader2 className="h-5 w-5 animate-spin text-signal-cyan" aria-hidden />
      <span className="text-sm">{label}</span>
    </Card>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <Card className="flex min-h-40 flex-col items-center justify-center text-center">
      <Database className="mb-3 h-6 w-6 text-slate-500" aria-hidden />
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      <p className="mt-2 max-w-md text-sm text-slate-400">{description}</p>
    </Card>
  );
}

export function ErrorState({ error, title = "Backend data unavailable" }: { error: unknown; title?: string }) {
  return (
    <Card className="border-rose-400/25 bg-rose-500/[0.06]">
      <div className="flex gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-rose-300" aria-hidden />
        <div>
          <h3 className="text-sm font-semibold text-rose-100">{title}</h3>
          <p className="mt-1 text-sm text-rose-100/80">{getErrorMessage(error)}</p>
          <p className="mt-2 text-xs uppercase tracking-[0.16em] text-rose-100/60">{getErrorCode(error)}</p>
        </div>
      </div>
    </Card>
  );
}

export function CapabilityGap({ title, description }: { title: string; description: string }) {
  return (
    <Card className="border-amber-300/20 bg-amber-300/[0.055]">
      <h3 className="text-sm font-semibold text-amber-100">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-amber-100/72">{description}</p>
    </Card>
  );
}
