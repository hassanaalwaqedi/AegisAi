"use client";

import { useMemo } from "react";
import { RiskAnalyticsWorkspace } from "@/components/analytics/risk-analytics-workspace";
import { AppShell } from "@/components/layout/app-shell";
import { useTranslations } from "next-intl";
import { useAlertCountQuery, useAlertsQuery, useCamerasQuery, usePersistedEvidenceQuery, useStatisticsQuery } from "@/hooks/use-aegis-api";

export default function AnalyticsPage() {
  const t = useTranslations("analytics");
  const statisticsQuery = useStatisticsQuery();
  const alertsQuery = useAlertsQuery(true, 100);
  const alertCountQuery = useAlertCountQuery();
  const camerasQuery = useCamerasQuery();
  const evidenceQuery = usePersistedEvidenceQuery();
  const retry = () => {
    void Promise.all([statisticsQuery.refetch(), alertsQuery.refetch(), alertCountQuery.refetch(), camerasQuery.refetch(), evidenceQuery.refetch()]);
  };

  return (
    <AppShell>
      <section className="mx-auto w-full max-w-[1800px] px-4 py-7 sm:px-6 lg:px-8" aria-labelledby="analytics-overview-title">
        <header className="flex flex-col gap-5 border-b border-white/[0.08] pb-6 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-signal-cyan">{t("commandAnalytics")}</p>
            <h1 id="analytics-overview-title" className="mt-2 text-3xl font-semibold tracking-tight text-white sm:text-4xl">{t("title")}</h1>
            <p className="mt-2 text-sm text-slate-400 sm:text-base">{t("subtitle")}</p>
          </div>
        </header>
        <RiskAnalyticsWorkspace
          statistics={statisticsQuery.data}
          activeAlerts={alertsQuery.data}
          activeAlertCount={alertCountQuery.data?.active}
          cameras={camerasQuery.data?.cameras ?? []}
          statisticsLoading={statisticsQuery.isLoading}
          statisticsUnavailable={statisticsQuery.isError}
          alertsUnavailable={alertsQuery.isError || alertCountQuery.isError}
          camerasUnavailable={camerasQuery.isError}
          evidenceAvailable={evidenceQuery.isSuccess}
          evidenceUnavailable={evidenceQuery.isError}
          dataUpdatedAt={statisticsQuery.dataUpdatedAt}
          onRetry={retry}
        />
      </section>
    </AppShell>
  );
}
