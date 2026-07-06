import { RiskBadge } from "@/components/dashboard/risk-badge";
import { EmptyState } from "@/components/layout/states";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDecimal, formatPercent } from "@/lib/data-format";
import type { SemanticResultsResponse } from "@/types";

type SemanticResultsProps = {
  data?: SemanticResultsResponse;
};

export function SemanticResults({ data }: SemanticResultsProps) {
  if (!data || data.results.length === 0) {
    return (
      <EmptyState
        title="No semantic results returned"
        description="GET /semantic/results returned no matches. Submit a semantic prompt or verify the semantic layer is enabled on the backend."
      />
    );
  }

  return (
    <Card className="overflow-hidden p-0">
      <CardHeader className="p-5 pb-3">
        <div>
          <CardTitle>Semantic Results</CardTitle>
          <p className="mt-1 text-sm text-slate-400">
            {data.semantic_matches} semantic matches across {data.total_tracks} returned tracks
          </p>
        </div>
      </CardHeader>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[780px] border-collapse text-left text-sm">
          <thead className="border-y border-white/10 bg-white/[0.035] text-xs uppercase tracking-[0.14em] text-slate-500">
            <tr>
              <th className="px-5 py-3 font-medium">Track ID</th>
              <th className="px-5 py-3 font-medium">Base class</th>
              <th className="px-5 py-3 font-medium">Semantic label</th>
              <th className="px-5 py-3 font-medium">Semantic confidence</th>
              <th className="px-5 py-3 font-medium">Risk score</th>
              <th className="px-5 py-3 font-medium">Matched phrase</th>
              <th className="px-5 py-3 font-medium">Behaviors</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/8">
            {data.results.map((result) => (
              <tr key={result.track_id} className="bg-command-900/30">
                <td className="px-5 py-4 font-mono text-signal-cyan">{result.track_id}</td>
                <td className="px-5 py-4 text-white">{result.base_class}</td>
                <td className="px-5 py-4 text-slate-300">{result.semantic_label ?? "Not returned"}</td>
                <td className="px-5 py-4 text-slate-300">{formatPercent(result.semantic_confidence)}</td>
                <td className="px-5 py-4">
                  <div className="flex items-center gap-2">
                    <RiskBadge level={result.risk_score >= 0.75 ? "CRITICAL" : result.risk_score >= 0.5 ? "HIGH" : result.risk_score >= 0.25 ? "MEDIUM" : "LOW"} />
                    <span className="text-slate-300">{formatDecimal(result.risk_score, 2)}</span>
                  </div>
                </td>
                <td className="px-5 py-4 text-slate-300">{result.matched_phrase ?? "Not returned"}</td>
                <td className="px-5 py-4 text-slate-300">{result.behaviors.length ? result.behaviors.join(", ") : "Not returned"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
