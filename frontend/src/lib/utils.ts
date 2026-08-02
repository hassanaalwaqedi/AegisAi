import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function formatTime(value?: string) {
  if (!value) return "Just now";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat("en", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(date);
}

export function riskToScore(level: string) {
  const map: Record<string, number> = {
    LOW: 0.18,
    MEDIUM: 0.44,
    HIGH: 0.74,
    CRITICAL: 0.92
  };
  return map[level.toUpperCase()] ?? 0.25;
}
