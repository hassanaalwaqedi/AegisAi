"use client";

import type { LucideIcon } from "lucide-react";
import { ArrowUpRight } from "lucide-react";
import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";
import type { Availability } from "@/lib/intelligence-context";

export function OperationalNode({
  title, label, value, detail, status, icon: Icon, active = false, onClick, children,
}: {
  title: string;
  label: string;
  value: string;
  detail?: string;
  status: Availability;
  icon: LucideIcon;
  active?: boolean;
  onClick?: () => void;
  children?: React.ReactNode;
}) {
  const t = useTranslations("intelligence.operator.status");
  const content = <>
    <header><span className="intelligence-node-icon"><Icon aria-hidden /></span><div><small>{label}</small><h2>{title}</h2></div><strong>{value}</strong></header>
    {children}
    {detail ? <p>{detail}</p> : null}
    <footer><span className="intelligence-state-dot" data-status={status} /><span>{t(status)}</span>{onClick ? <ArrowUpRight aria-hidden /> : null}</footer>
  </>;

  return onClick ? <button type="button" onClick={onClick} className={cn("intelligence-node", active && "is-active")} data-status={status}>{content}</button>
    : <section className={cn("intelligence-node", active && "is-active")} data-status={status}>{content}</section>;
}
