"use client";

import { IntelligenceCommandCenter } from "@/components/intelligence/intelligence-command-center";
import { AppShell } from "@/components/layout/app-shell";
import { useIntelligenceContext } from "@/hooks/useIntelligenceContext";

export default function IntelligencePage() {
  return <AppShell><IntelligenceCommandCenter state={useIntelligenceContext()} /></AppShell>;
}
