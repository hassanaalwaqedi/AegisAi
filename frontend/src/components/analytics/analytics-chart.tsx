"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { CapabilityGap } from "@/components/layout/states";

const COLORS = ["#2dd4bf", "#f6c453", "#ff4f64", "#9a8cff", "#38d6ff"];

type AnalyticsChartProps = {
  title: string;
  description: string;
  unavailable: string;
  data: Array<Record<string, string | number>>;
  kind: "bar" | "line" | "pie";
  xKey: string;
  yKey: string;
};

export function AnalyticsChart({ title, description, unavailable, data, kind, xKey, yKey }: AnalyticsChartProps) {
  if (data.length === 0) {
    return <CapabilityGap title={`${title} unavailable`} description={unavailable} />;
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{title}</CardTitle>
          <p className="mt-1 text-sm text-slate-400">{description}</p>
        </div>
      </CardHeader>

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          {kind === "bar" ? (
            <BarChart data={data}>
              <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
              <XAxis dataKey={xKey} tick={{ fill: "#94a3b8", fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "#0d1422", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8 }} />
              <Bar dataKey={yKey} fill="#38d6ff" radius={[4, 4, 0, 0]} />
            </BarChart>
          ) : kind === "line" ? (
            <LineChart data={data}>
              <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
              <XAxis dataKey={xKey} tick={{ fill: "#94a3b8", fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "#0d1422", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8 }} />
              <Line type="monotone" dataKey={yKey} stroke="#2dd4bf" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          ) : (
            <PieChart>
              <Tooltip contentStyle={{ background: "#0d1422", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8 }} />
              <Pie data={data} dataKey={yKey} nameKey={xKey} innerRadius={62} outerRadius={100} paddingAngle={2}>
                {data.map((entry, index) => (
                  <Cell key={String(entry[xKey])} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          )}
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
