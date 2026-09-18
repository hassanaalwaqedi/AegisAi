"use client";

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

  return (
    <nav className="flex max-w-full gap-1 overflow-hidden rounded-lg border border-white/10 bg-white/[0.04] p-1 lg:max-w-none">
      {navItems.map((item) => {
        const Icon = item.icon;
        const active = pathname === item.href;
        const label = t(item.labelKey);

        return (
          <Link
            key={item.href}
            href={item.href as any}
            aria-label={label}
            title={label}
            className={cn(
              "inline-flex min-h-9 shrink-0 items-center justify-center gap-2 rounded-md px-2.5 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white xl:px-3",
              active && "bg-signal-cyan/12 text-signal-cyan"
            )}
          >
            <Icon className="h-4 w-4" aria-hidden />
            <span className="hidden xl:inline">{label}</span>
          </Link>
        );
      })}
      <div className="ms-auto flex items-center border-s border-white/10 ps-1 rtl:border-s-0 rtl:border-e rtl:ps-0 rtl:pe-1">
        <LanguageSwitcher />
      </div>
    </nav>
  );
}
