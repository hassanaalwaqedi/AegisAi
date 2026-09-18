import { ShieldCheck } from "lucide-react";
import { Navigation } from "@/components/layout/navigation";
import { Link } from "@/i18n/routing";
import { useTranslations } from "next-intl";

export function AppShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations("app");

  return (
    <div className="min-h-screen bg-command-950 text-slate-100">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-command-950/88 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1800px] flex-col gap-3 px-4 py-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <Link href="/" className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-md border border-signal-cyan/40 bg-signal-cyan/10 text-signal-cyan">
              <ShieldCheck className="h-5 w-5" aria-hidden />
            </span>
            <span>
              <span className="block text-sm font-semibold uppercase tracking-[0.18em] text-signal-cyan">{t("title")}</span>
              <span className="block text-xs text-slate-400">{t("subtitle")}</span>
            </span>
          </Link>

          <Navigation />
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
