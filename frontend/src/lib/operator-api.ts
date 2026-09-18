import { z } from "zod";

import { appConfig } from "@/lib/config";

const operatorTraceSchema = z.object({
  key: z.string(),
  label: z.string(),
  status: z.string(),
});

const operatorSourceSchema = z.object({
  type: z.string(),
  id: z.string().nullable().optional(),
  label: z.string(),
});

export const operatorExecutionSchema = z.object({
  action: z.string(),
  intent: z.string(),
  answer: z.string(),
  panel: z.string(),
  target: z.string().nullable().optional(),
  result: z.record(z.string(), z.unknown()),
  sources: z.array(operatorSourceSchema),
  trace: z.array(operatorTraceSchema),
  response_language: z.string(),
  error: z.string().nullable().optional(),
});

export type OperatorExecution = z.infer<typeof operatorExecutionSchema>;

export type OperatorCommandContext = {
  previous_intent?: string;
  previous_query?: string;
  previous_evidence_id?: string;
  selected_camera_id?: string;
  selected_track_id?: string;
};

export async function executeOperatorCommand(
  message: string,
  context: OperatorCommandContext = {},
  signal?: AbortSignal,
): Promise<OperatorExecution> {
  const response = await fetch(`${appConfig.apiUrl}/api/ai/operator/execute`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ message, ...context }),
    signal,
  });
  if (!response.ok) throw new Error(`Aegis operator request failed with HTTP ${response.status}.`);
  const payload = operatorExecutionSchema.safeParse(await response.json());
  if (!payload.success) throw new Error("Aegis operator returned an invalid response.");
  return payload.data;
}
