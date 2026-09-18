"use client";

import { useLocale, useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/routing";
import { Globe } from "lucide-react";
import { cn } from "@/lib/utils";

export function LanguageSwitcher() {
  const locale = useLocale();
  const t = useTranslations("common");
  const pathname = usePathname();

  // If we are currently on Arabic, switch to English, else Arabic
  const targetLocale = locale === "ar" ? "en" : "ar";
  const label = locale === "ar" ? "English" : "العربية";

  return (
    <Link
      href={pathname}
      locale={targetLocale}
      className={cn(
        "inline-flex min-h-9 items-center justify-center gap-2 rounded-md px-2 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white sm:px-3"
      )}
      title={label}
    >
      <Globe className="h-4 w-4" aria-hidden />
      <span className="hidden sm:inline">{label}</span>
    </Link>
  );
}
