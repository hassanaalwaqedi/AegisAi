"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Binary, Camera, Cctv, Home, RadioTower, Search } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Overview", icon: Home },
  { href: "/dashboard", label: "Dashboard", icon: Cctv },
  { href: "/cameras", label: "Cameras", icon: Camera },
  { href: "/events", label: "Events", icon: RadioTower },
  { href: "/tracks", label: "Tracks", icon: Binary },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/semantic", label: "Semantic", icon: Search }
];

export function Navigation() {
  const pathname = usePathname();

  return (
    <nav className="flex max-w-full gap-1 overflow-x-auto rounded-lg border border-white/10 bg-white/[0.04] p-1 lg:max-w-[56vw] xl:max-w-none">
      {navItems.map((item) => {
        const Icon = item.icon;
        const active = pathname === item.href;

        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "inline-flex min-h-9 shrink-0 items-center gap-2 rounded-md px-3 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white",
              active && "bg-signal-cyan/12 text-signal-cyan"
            )}
          >
            <Icon className="h-4 w-4" aria-hidden />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
