"use client";

import { AnalyticsChart } from "@/components/analytics/analytics-chart";
import { ApiStatusBanner } from "@/components/layout/api-status-banner";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { ErrorState, LoadingState } from "@/components/layout/states";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { useStatisticsQuery } from "@/hooks/use-aegis-api";
import {
  alertsBySeverityData,
  crowdDensityTrendData,
  detectionsOverTimeData,
  formatDecimal,
  formatNumber,
  getCrowdDetected,
  getCrowdMetric,
  riskDistributionData
} from "@/lib/data-format";

export default function AnalyticsPage() {
  const statisticsQuery = useStatisticsQuery();
  const statistics = statisticsQuery.data;

  return (
    <AppShell>
      <section className="section-shell">
        <PageHeader
          eyebrow="Analytics"
          title="Risk Analytics"
          description="Charts render only from fields returned by GET /statistics. Missing analytics are presented as backend capability gaps."
          badge="GET /statistics"
        />

        <ApiStatusBanner endpoints={[{ name: "/statistics", query: statisticsQuery }]} />

        {statisticsQuery.isLoading ? <LoadingState label="Loading statistics from backend" /> : null}
        {statisticsQuery.isError ? <ErrorState error={statisticsQuery.error} title="/statistics unavailable" /> : null}

        {statistics ? (
          <div className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Metric label="Persons" value={formatNumber(getCrowdMetric(statistics, "person_count"))} />
              <Metric label="Vehicles" value={formatNumber(getCrowdMetric(statistics, "vehicle_count"))} />
              <Metric label="Max density" value={formatDecimal(getCrowdMetric(statistics, "max_density"), 1)} />
              <Metric label="Crowd detected" value={typeof getCrowdDetected(statistics) === "boolean" ? (getCrowdDetected(statistics) ? "Yes" : "No") : "Not returned"} />
            </div>

            <div className="grid gap-5 xl:grid-cols-2">
              <AnalyticsChart
                title="Detections over time"
                description="Requires detections_over_time from /statistics"
                unavailable="Analytics data not available from backend: detections_over_time was not returned by /statistics."
                data={detectionsOverTimeData(statistics)}
                kind="line"
                xKey="time"
                yKey="detections"
              />
              <AnalyticsChart
                title="Alerts by severity"
                description="Requires alerts_by_severity from /statistics"
                unavailable="Analytics data not available from backend: alerts_by_severity was not returned by /statistics."
                data={alertsBySeverityData(statistics)}
                kind="bar"
                xKey="severity"
                yKey="count"
              />
              <AnalyticsChart
                title="Risk level distribution"
                description="Uses risk.distribution from /statistics"
                unavailable="Analytics data not available from backend: risk.distribution was not returned by /statistics."
                data={riskDistributionData(statistics)}
                kind="pie"
                xKey="level"
                yKey="count"
              />
              <AnalyticsChart
                title="Crowd density trend"
                description="Requires crowd_density_trend or crowd.density_trend from /statistics"
                unavailable="Analytics data not available from backend: crowd density trend fields were not returned by /statistics."
                data={crowdDensityTrendData(statistics)}
                kind="line"
                xKey="time"
                yKey="density"
              />
            </div>
          </div>
        ) : null}
      </section>
    </AppShell>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <CardHeader className="mb-0 p-0">
        <CardTitle className="text-sm text-slate-400">{label}</CardTitle>
      </CardHeader>
      <p className="mt-3 text-2xl font-semibold text-white">{value}</p>
    </Card>
  );
}
