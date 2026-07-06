import { cn } from "@/lib/utils";

type BadgeProps = React.HTMLAttributes<HTMLSpanElement> & {
  variant?: "default" | "success" | "warning" | "danger" | "critical" | "outline";
};

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center rounded-md border px-2 py-0.5 text-xs font-medium",
        variant === "default" && "border-slate-500/30 bg-slate-400/10 text-slate-200",
        variant === "success" && "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
        variant === "warning" && "border-amber-400/35 bg-amber-400/10 text-amber-200",
        variant === "danger" && "border-rose-400/35 bg-rose-400/10 text-rose-200",
        variant === "critical" && "border-fuchsia-300/35 bg-fuchsia-400/10 text-fuchsia-100",
        variant === "outline" && "border-white/15 bg-transparent text-slate-300",
        className
      )}
      {...props}
    />
  );
}
