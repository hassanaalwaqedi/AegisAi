"use client";

import { Select } from "@/components/ui/select";
import type { RiskEvent } from "@/types";
import { getEventObject } from "@/lib/data-format";

export type EventFilters = {
  severity: string;
  objectType: string;
  riskLevel: string;
  timeWindow: string;
};

type EventFiltersProps = {
  events: RiskEvent[];
  value: EventFilters;
  onChange: (value: EventFilters) => void;
};

export function EventFiltersBar({ events, value, onChange }: EventFiltersProps) {
  const objectTypes = Array.from(new Set(events.map(getEventObject).filter((item) => item !== "Not returned"))).sort();

  return (
    <div className="grid gap-3 rounded-lg border border-white/10 bg-white/[0.04] p-4 sm:grid-cols-2 xl:grid-cols-4">
      <FilterSelect
        label="Severity"
        value={value.severity}
        onChange={(severity) => onChange({ ...value, severity })}
        options={["All", "info", "warning", "LOW", "MEDIUM", "HIGH", "CRITICAL"]}
      />
      <FilterSelect
        label="Object type"
        value={value.objectType}
        onChange={(objectType) => onChange({ ...value, objectType })}
        options={["All", ...objectTypes]}
      />
      <FilterSelect
        label="Risk level"
        value={value.riskLevel}
        onChange={(riskLevel) => onChange({ ...value, riskLevel })}
        options={["All", "LOW", "MEDIUM", "HIGH", "CRITICAL"]}
      />
      <FilterSelect
        label="Time"
        value={value.timeWindow}
        onChange={(timeWindow) => onChange({ ...value, timeWindow })}
        options={["All", "Last hour", "Last day"]}
      />
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs uppercase tracking-[0.14em] text-slate-500">{label}</span>
      <Select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </Select>
    </label>
  );
}
