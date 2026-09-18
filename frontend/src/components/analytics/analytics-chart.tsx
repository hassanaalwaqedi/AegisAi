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
import { Activity } from "lucide-react";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";

const COLORS = ["#2dd4bf", "#f6c453", "#ff4f64", "#9a8cff", "#38d6ff"];

type AnalyticsChartProps = {
  title: string;
  description: string;
  data: Array<Record<string, string | number>>;
  kind: "bar" | "line" | "pie";
  xKey: string;
  yKey: string;
  color?: string;
  emptyTitle?: string;
  emptyDescription?: string;
};

export function AnalyticsChart({ title, description, data, kind, xKey, yKey, color = "#38d6ff", emptyTitle = "No analytics data available yet.", emptyDescription = "Connect event history or enable analytics persistence." }: AnalyticsChartProps) {
  if (data.length === 0) {
    return (
      <Card className="min-h-[300px]">
        <CardHeader>
          <div>
            <CardTitle>{title}</CardTitle>
            <p className="mt-1 text-sm text-slate-400">{description}</p>
          </div>
        </CardHeader>
        <div className="flex h-48 flex-col items-center justify-center rounded-lg border border-white/[0.08] bg-black/20 px-6 text-center">
          <Activity className="h-6 w-6 text-slate-600" aria-hidden />
          <p className="mt-3 text-sm font-medium text-slate-200">{emptyTitle}</p>
          <p className="mt-1 max-w-sm text-sm text-slate-500">{emptyDescription}</p>
        </div>
      </Card>
    );
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
              <Bar dataKey={yKey} fill={color} radius={[4, 4, 0, 0]} />
            </BarChart>
          ) : kind === "line" ? (
            <LineChart data={data}>
              <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
              <XAxis dataKey={xKey} tick={{ fill: "#94a3b8", fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "#0d1422", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8 }} />
              <Line type="monotone" dataKey={yKey} stroke={color} strokeWidth={2} dot={{ r: 3 }} />
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
