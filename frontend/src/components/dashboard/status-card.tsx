import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type StatusCardProps = {
  label: string;
  value: string;
  detail?: string;
  icon: LucideIcon;
  tone?: "neutral" | "good" | "warning" | "danger";
};

export function StatusCard({ label, value, detail, icon: Icon, tone = "neutral" }: StatusCardProps) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{label}</p>
          <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
          {detail ? <p className="mt-1 text-sm text-slate-400">{detail}</p> : null}
        </div>
        <span
          className={cn(
            "flex h-10 w-10 items-center justify-center rounded-md border",
            tone === "neutral" && "border-slate-400/20 bg-slate-400/10 text-slate-300",
            tone === "good" && "border-emerald-300/30 bg-emerald-400/10 text-emerald-200",
            tone === "warning" && "border-amber-300/30 bg-amber-300/10 text-amber-200",
            tone === "danger" && "border-rose-300/30 bg-rose-400/10 text-rose-200"
          )}
        >
          <Icon className="h-5 w-5" aria-hidden />
        </span>
      </div>
    </Card>
  );
}
