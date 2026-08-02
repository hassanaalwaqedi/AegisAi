import { RiskBadge } from "@/components/dashboard/risk-badge";
import { EmptyState } from "@/components/layout/states";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDecimal, formatPercent, formatTimestamp } from "@/lib/data-format";
import type { SemanticResultsResponse } from "@/types";

type SemanticResultsProps = {
  data?: SemanticResultsResponse;
};

export function SemanticResults({ data }: SemanticResultsProps) {
  if (!data || data.results.length === 0) {
    return (
      <EmptyState
        title={data?.query ? "No verified matches yet" : "Search live security evidence"}
        description={data?.query ? `No current track, event, or crowd metric matches “${data.query}”. Keep the camera running or try a broader query.` : "Submit a query to search the current live tracks, recent events, and measured crowd metrics."}
      />
    );
  }

  return (
    <Card className="overflow-hidden p-0">
      <CardHeader className="p-5 pb-3">
        <div>
          <CardTitle>Verified matches</CardTitle>
          <p className="mt-1 text-sm text-slate-400">
            {data.semantic_matches} match{data.semantic_matches === 1 ? "" : "es"} for “{data.query ?? "live evidence"}” · evaluated {data.evaluated_tracks ?? 0} tracks and {data.evaluated_events ?? 0} recent events in {formatDecimal(data.execution_ms ?? 0, 1)} ms
          </p>
        </div>
      </CardHeader>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[920px] border-collapse text-left text-sm">
          <thead className="border-y border-white/10 bg-white/[0.035] text-xs uppercase tracking-[0.14em] text-slate-500">
            <tr>
              <th className="px-5 py-3 font-medium">Evidence</th>
              <th className="px-5 py-3 font-medium">Object</th>
              <th className="px-5 py-3 font-medium">Source</th>
              <th className="px-5 py-3 font-medium">Match confidence</th>
              <th className="px-5 py-3 font-medium">Risk score</th>
              <th className="px-5 py-3 font-medium">Camera / time</th>
              <th className="px-5 py-3 font-medium">Verified evidence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/8">
            {data.results.map((result) => (
              <tr key={result.track_id} className="bg-command-900/30">
                <td className="px-5 py-4 font-mono text-signal-cyan">{result.track_id}</td>
                <td className="px-5 py-4 text-white">{result.base_class}</td>
                <td className="px-5 py-4"><Badge variant={result.source === "statistics" ? "success" : result.source === "event" ? "warning" : "outline"}>{result.source ?? "track"}</Badge></td>
                <td className="px-5 py-4 text-slate-300">{formatPercent(result.semantic_confidence)}</td>
                <td className="px-5 py-4">
                  <div className="flex items-center gap-2">
                    <RiskBadge level={result.risk_score >= 0.75 ? "CRITICAL" : result.risk_score >= 0.5 ? "HIGH" : result.risk_score >= 0.25 ? "MEDIUM" : "LOW"} />
                    <span className="text-slate-300">{formatDecimal(result.risk_score, 2)}</span>
                  </div>
                </td>
                <td className="px-5 py-4 text-slate-300"><p>{result.camera_id ?? result.zone ?? "System metric"}</p><p className="mt-1 text-xs text-slate-500">{result.timestamp ? formatTimestamp(result.timestamp) : "Current state"}</p></td>
                <td className="px-5 py-4 text-slate-300"><p>{result.evidence?.[0] ?? result.semantic_label ?? "Verified live data"}</p>{result.behaviors.length ? <p className="mt-1 text-xs text-slate-500">{result.behaviors.join(", ")}</p> : null}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
