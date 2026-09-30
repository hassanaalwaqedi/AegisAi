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
      aria-label={label}
      className={cn(
        "aegis-language-switcher"
      )}
      title={label}
    >
      <Globe aria-hidden />
      <span>{label}</span>
    </Link>
  );
}
