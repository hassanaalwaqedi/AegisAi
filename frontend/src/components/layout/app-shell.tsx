import Link from "next/link";
import { Activity, ShieldCheck } from "lucide-react";
import { Navigation } from "@/components/layout/navigation";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-command-950 text-slate-100">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-command-950/88 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1800px] flex-col gap-3 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <Link href="/" className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-md border border-signal-cyan/40 bg-signal-cyan/10 text-signal-cyan">
              <ShieldCheck className="h-5 w-5" aria-hidden />
            </span>
            <span>
              <span className="block text-sm font-semibold uppercase tracking-[0.18em] text-signal-cyan">AegisAI</span>
              <span className="block text-xs text-slate-400">Risk Intelligence Platform</span>
            </span>
          </Link>

          <Navigation />

          <div className="hidden items-center gap-2 text-xs text-slate-400 xl:flex">
            <Activity className="h-4 w-4 text-signal-teal" aria-hidden />
            Video - Detection - Tracking - Behavior - Risk - Response
          </div>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
