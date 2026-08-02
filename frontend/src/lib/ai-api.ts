/**
 * AegisAI - AI API Client
 *
 * Connects the frontend to the AI orchestrator backend.
 * All AI interactions go through: Frontend → FastAPI → Gemini → Frontend
 */

import { appConfig } from "@/lib/config";

const API_BASE = appConfig.apiUrl;

const headers: Record<string, string> = {
  "Content-Type": "application/json",
};

// ── Types ──

export interface ChatResponse {
  intent: string;
  answer: string;
  actions: { type: string; target: string; label: string }[];
  sources: { type: string; id?: string; label: string }[];
  confidence: number;
  latency_ms: number;
  error?: string;
}

export interface SystemMetrics {
  cameras_online: number;
  cameras_total: number;
  database: string;
  redis: string;
  pipeline: string;
  gpu: { available: boolean; device?: string; memory_allocated_mb?: number; memory_total_mb?: number };
  pipeline_stats: { pipeline_running: boolean; stages: any[] };
  alerts_today: number;
}

export interface AISuggestion {
  id: string;
  text: string;
  icon: string;
  priority: "urgent" | "recommended" | "optional";
}

// ── API Functions ──

export async function sendChatMessage(message: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/ai/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`AI chat failed: ${res.status}`);
  return res.json();
}

export async function fetchSystemMetrics(): Promise<SystemMetrics | null> {
  try {
    const res = await fetch(`${API_BASE}/api/ai/metrics`, { headers });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchAISuggestions(): Promise<AISuggestion[]> {
  try {
    const res = await fetch(`${API_BASE}/api/ai/suggestions`, { headers });
    if (!res.ok) return [];
    const data = await res.json();
    return data.suggestions || [];
  } catch {
    return [];
  }
}

export async function fetchSystemContext(): Promise<any> {
  try {
    const res = await fetch(`${API_BASE}/api/ai/context`, { headers });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}
