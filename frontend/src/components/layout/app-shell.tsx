import { ShieldCheck } from "lucide-react";
import { Navigation } from "@/components/layout/navigation";
import { Link } from "@/i18n/routing";
import { useTranslations } from "next-intl";

export function AppShell({ children }: { children: React.ReactNode }) {
  const t = useTranslations("app");

  return (
    <div className="aegis-app-shell min-h-screen bg-command-950 text-slate-100">
      <header className="aegis-shell-header">
        <div className="aegis-shell-rail">
          <Link href="/" className="aegis-shell-mark" aria-label={t("title")}>
            <span>
              <ShieldCheck aria-hidden />
            </span>
            <strong>{t("title")}</strong>
          </Link>

          <Navigation />
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
