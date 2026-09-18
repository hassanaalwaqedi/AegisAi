import { act, renderHook, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useOperatorScene } from "./use-operator-scene";
import { executeOperatorCommand, type OperatorExecution } from "@/lib/operator-api";
import { operatorPresence } from "@/lib/operator-scene";

vi.mock("@/lib/operator-api", () => ({ executeOperatorCommand: vi.fn() }));
const execute = vi.mocked(executeOperatorCommand);
const events: OperatorExecution = { action: "RISK_QUERY", intent: "RISK", answer: "Found 2 event records.", panel: "events", target: "/events?risk=high", result: { events: [{ event_id: "one" }, { event_id: "two" }] }, sources: [], trace: [], response_language: "English" };
beforeEach(() => execute.mockReset());
afterEach(cleanup);

describe("persistent operator scene", () => {
  it("keeps normal results on stage, selects an ordinal, and sends the selected ID for related evidence", async () => {
    execute.mockResolvedValue(events);
    const navigate = vi.fn();
    const { result } = renderHook(() => useOperatorScene(navigate));
    await act(async () => { await result.current.run("Show high-risk events"); });
    expect(navigate).not.toHaveBeenCalled();
    await act(async () => { await result.current.run("Open the second one"); });
    expect(result.current.selectedId).toBe("two");
    expect(execute).toHaveBeenCalledTimes(1);
    await act(async () => { await result.current.run("Show related evidence"); });
    expect(execute.mock.calls[1][1]).toMatchObject({ previous_evidence_id: "two", previous_query: "Show high-risk events" });
  });

  it("navigates only on an explicit full-view request", async () => {
    execute.mockResolvedValue(events);
    const navigate = vi.fn();
    const { result } = renderHook(() => useOperatorScene(navigate));
    await act(async () => { await result.current.run("Show high-risk events"); });
    await act(async () => { await result.current.run("Open full details"); });
    expect(navigate).toHaveBeenCalledWith("/events?risk=high&event=one");
  });

  it("rejects out-of-range selections without inventing a result", async () => {
    execute.mockResolvedValue(events);
    const { result } = renderHook(() => useOperatorScene(vi.fn()));
    await act(async () => { await result.current.run("Show events"); });
    await act(async () => { await result.current.run("Open the fifth one"); });
    expect(result.current.error).toMatch(/not in the current projection/);
    expect(result.current.selectedId).toBe("one");
  });

  it("ignores a late response after a new command has completed", async () => {
    let finish!: (value: OperatorExecution) => void;
    execute.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; })).mockResolvedValueOnce({ ...events, answer: "New result" });
    const { result } = renderHook(() => useOperatorScene(vi.fn()));
    let first!: Promise<void>;
    act(() => { first = result.current.run("Show events"); });
    expect(result.current.pending).toBe(true);
    await act(async () => { await result.current.run("Show high-risk events"); });
    await act(async () => { finish(events); await first; });
    expect(result.current.execution?.answer).toBe("New result");
  });

  it("ties presence to real capture, requests, playback and projection state", () => {
    const base = { voice: "off" as const, capturing: false, pending: false, toolPending: false, execution: null, warning: false };
    expect(operatorPresence(base)).toBe("idle");
    expect(operatorPresence({ ...base, voice: "listening" })).toBe("idle");
    expect(operatorPresence({ ...base, voice: "listening", capturing: true })).toBe("listening");
    expect(operatorPresence({ ...base, pending: true })).toBe("executing");
    expect(operatorPresence({ ...base, voice: "thinking" })).toBe("thinking");
    expect(operatorPresence({ ...base, voice: "speaking" })).toBe("speaking");
    expect(operatorPresence({ ...base, execution: events })).toBe("presenting");
    expect(operatorPresence({ ...base, warning: true })).toBe("warning");
  });
});
