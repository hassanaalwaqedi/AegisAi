"use client";
import { Suspense } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { EvidenceSearchWorkspace } from "@/components/semantic/evidence-search-workspace";

export default function SemanticPage() {
  return <AppShell><Suspense fallback={null}><EvidenceSearchWorkspace /></Suspense></AppShell>;
}
