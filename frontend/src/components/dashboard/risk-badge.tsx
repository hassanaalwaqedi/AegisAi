import { Badge } from "@/components/ui/badge";
import type { RiskLevel } from "@/types";

type RiskBadgeProps = {
  level?: RiskLevel | string;
};

export function RiskBadge({ level }: RiskBadgeProps) {
  if (!level) return <Badge variant="outline">Not returned</Badge>;

  const normalized = level.toUpperCase();
  const variant =
    normalized === "LOW"
      ? "success"
      : normalized === "MEDIUM" || normalized === "CANDIDATE_MEDIUM"
        ? "warning"
        : normalized === "HIGH"
          ? "danger"
          : normalized === "CRITICAL"
            ? "critical"
            : "outline";

  return <Badge variant={variant}>{normalized === "CANDIDATE_MEDIUM" ? "CANDIDATE MEDIUM" : normalized}</Badge>;
}
