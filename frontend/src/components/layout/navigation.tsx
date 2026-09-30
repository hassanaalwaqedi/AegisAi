"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/routing";
import { BarChart3, Binary, BrainCircuit, Camera, Cctv, RadioTower, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { LanguageSwitcher } from "./language-switcher";

const navItems = [
  { href: "/", labelKey: "intelligence", icon: BrainCircuit },
  { href: "/dashboard", labelKey: "dashboard", icon: Cctv },
  { href: "/cameras", labelKey: "cameras", icon: Camera },
  { href: "/events", labelKey: "events", icon: RadioTower },
  { href: "/tracks", labelKey: "tracks", icon: Binary },
  { href: "/analytics", labelKey: "analytics", icon: BarChart3 },
  { href: "/semantic", labelKey: "semantic", icon: Search }
];

export function Navigation() {
  const pathname = usePathname();
  const t = useTranslations("navigation");
  const [engagedDomain, setEngagedDomain] = useState<string | null>(null);

  useEffect(() => {
    const handleDomainFocus = (event: Event) => {
      const detail = (event as CustomEvent<{ domain?: string | null }>).detail;
      setEngagedDomain(detail?.domain ?? null);
    };
    window.addEventListener("aegis:domain-focus", handleDomainFocus);
    return () => window.removeEventListener("aegis:domain-focus", handleDomainFocus);
  }, []);

  const engagedHref = engagedDomain === "cameras" ? "/cameras"
    : engagedDomain === "events" || engagedDomain === "risk" || engagedDomain === "incidents" ? "/events"
      : engagedDomain === "tracking" ? "/tracks"
        : engagedDomain === "analytics" ? "/analytics"
          : engagedDomain === "evidence" || engagedDomain === "semantic" ? "/semantic"
            : null;

  return (
    <nav className="aegis-nav-rail" aria-label="Primary navigation">
      {navItems.map((item) => {
        const Icon = item.icon;
        const active = pathname === item.href;
        const engaged = engagedHref === item.href;
        const label = t(item.labelKey);

        return (
          <Link
            key={item.href}
            href={item.href as any}
            aria-label={label}
            title={label}
            data-active={active}
            data-engaged={engaged}
            className={cn(
              "aegis-nav-link",
              active && "is-active"
            )}
          >
            <Icon aria-hidden />
            <span>{label}</span>
          </Link>
        );
      })}
      <div className="aegis-nav-language">
        <LanguageSwitcher />
      </div>
    </nav>
  );
}
