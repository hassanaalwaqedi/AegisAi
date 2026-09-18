import { describe, expect, it } from "vitest";

import { analyticsCoverage, cameraRiskRanking, eventTypeBreakdown } from "@/lib/analytics-adapter";
import type { Camera, RiskEvent, StatisticsResponse } from "@/types";

describe("analytics adapter", () => {
  it("keeps missing backend analytics visibly missing instead of creating charts", () => {
    const partial = { crowd: { person_count: 2 } } as StatisticsResponse;
    const coverage = analyticsCoverage(partial, { camerasAvailable: true, evidenceAvailable: false, evidenceDegraded: false });

    expect(coverage.find((item) => item.label === "Time series")?.status).toBe("missing");
    expect(coverage.find((item) => item.label === "Camera ranking")?.status).toBe("missing");
    expect(eventTypeBreakdown(partial)).toEqual([]);
    expect(cameraRiskRanking([], [])).toEqual([]);
  });

  it("derives recent camera activity only from returned events", () => {
    const cameras = [{ camera_id: "north-gate", name: "North Gate", runtime: { status: "online" } }] as Camera[];
    const events = [
      { camera_id: "north-gate", event_type: "risk_alert", risk_level: "HIGH", timestamp: "2026-08-10T10:00:00Z" },
      { camera_id: "north-gate", event_type: "possible_assault", risk_level: "MEDIUM", timestamp: "2026-08-10T10:01:00Z" },
    ] as RiskEvent[];

    expect(cameraRiskRanking(events, cameras)).toMatchObject([{ cameraId: "north-gate", recentAlertCount: 1, recentEventCount: 2, highestRisk: "HIGH" }]);
    expect(eventTypeBreakdown({ events_by_type: { possible_assault: 1 } } as StatisticsResponse)).toEqual([{ eventType: "possible_assault", label: "Possible assault", count: 1 }]);
  });
});
