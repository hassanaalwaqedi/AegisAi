"use client";

import { useCallback, useState } from "react";
import { Command, Loader2, Send } from "lucide-react";

import { sendChatMessage, type ChatResponse } from "@/lib/ai-api";
import { availabilityLabel, type Availability } from "@/lib/intelligence-context";

interface CommandBarProps {
  chatAvailability: Availability;
  chatReason?: string | null;
}

/**
 * Text-only non-voice command entry. Native audio, microphone capture, and
 * transcript handling live in VoiceCopilot; this component never invokes
 * browser speech recognition or speech synthesis.
 */
export default function CommandBar({ chatAvailability, chatReason }: CommandBarProps) {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const enabled = chatAvailability === "live";
  const unavailableReason = chatReason ?? `Text AI chat is ${availabilityLabel(chatAvailability).toLowerCase()} in the current Intelligence context.`;

  const submit = useCallback(async (event: React.FormEvent) => {
    event.preventDefault();
    const message = query.trim();
    if (!enabled || !message || loading) return;
    setLoading(true);
    setError(null);
    setResponse(null);
    try {
      setResponse(await sendChatMessage(message));
      setQuery("");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Text AI chat could not be completed.");
    } finally {
      setLoading(false);
    }
  }, [enabled, loading, query]);

  return (
    <div className="w-full">
      <form onSubmit={submit} className="flex items-center gap-2 rounded-xl border border-signal-cyan/[0.08] bg-[#0a0f1a]/80 px-3 py-2">
        <Command size={14} className="shrink-0 text-signal-cyan/40" />
        <input value={query} onChange={(event) => setQuery(event.target.value)} disabled={!enabled || loading} placeholder={enabled ? "Ask the configured read-only AI service…" : unavailableReason} className="min-w-0 flex-1 bg-transparent text-[11px] text-white/90 outline-none placeholder:text-white/20 disabled:cursor-not-allowed" aria-describedby={!enabled ? "chat-capability-reason" : undefined} />
        <button type="submit" disabled={!enabled || !query.trim() || loading} className="rounded-lg p-1.5 text-signal-cyan disabled:opacity-30" title={enabled ? "Send text request" : unavailableReason}>{loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}</button>
      </form>
      {!enabled && <p id="chat-capability-reason" className="mt-1 text-center text-[9px] text-white/25">Text chat unavailable: {unavailableReason}</p>}
      {error && <p className="mt-1 text-center text-[9px] text-signal-red/85" role="alert">{error}</p>}
      {response && <p className="mt-1 rounded-lg border border-white/[0.05] bg-white/[0.02] p-2 text-[10px] text-white/70">{response.answer}</p>}
    </div>
  );
}
