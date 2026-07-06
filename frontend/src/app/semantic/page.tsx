"use client";

import { SemanticQueryBox } from "@/components/semantic/semantic-query-box";
import { SemanticResults } from "@/components/semantic/semantic-results";
import { ApiStatusBanner } from "@/components/layout/api-status-banner";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { ErrorState, LoadingState } from "@/components/layout/states";
import { useSemanticResultsQuery } from "@/hooks/use-aegis-api";

export default function SemanticPage() {
  const resultsQuery = useSemanticResultsQuery();

  return (
    <AppShell>
      <section className="section-shell">
        <PageHeader
          eyebrow="Semantic intelligence"
          title="Natural Language Risk Query"
          description="Submit operator prompts to the backend semantic layer and review only the real results returned by GET /semantic/results."
          badge="Semantic API"
        />

        <ApiStatusBanner endpoints={[{ name: "/semantic/results", query: resultsQuery }]} />

        <div className="grid gap-5 xl:grid-cols-[0.85fr_1.15fr]">
          <SemanticQueryBox />
          <div>
            {resultsQuery.isLoading ? <LoadingState label="Loading semantic results from backend" /> : null}
            {resultsQuery.isError ? <ErrorState error={resultsQuery.error} title="/semantic/results unavailable" /> : null}
            {resultsQuery.data ? <SemanticResults data={resultsQuery.data} /> : null}
          </div>
        </div>
      </section>
    </AppShell>
  );
}
