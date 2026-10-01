# Aegis Vision Agent — Internal Tool Inventory

The existing Gemini Live gateway remains the only voice investigation agent. It declares allow-listed Python tools through `LiveToolRegistry.declarations()` and executes each call on the backend in `aegis/intelligence/live_service.py`.

| Capability | Existing source | Phase 2 state |
| --- | --- | --- |
| Cameras, live events, current tracks, risk signals | `aegis/intelligence/live_tools.py` + `aegis/intelligence/context_service.py` | Reused |
| Pipeline/system health and CUDA memory/device | `get_pipeline_health`, `get_intelligence_context`, existing `aegis/ai/tools.py:get_gpu_usage` | Reused; GPU memory is not presented as utilization |
| Semantic evidence search | `search_live_evidence` | Reused; remains unavailable when the existing engine is unavailable |
| Event VLM comparison and incident VLM retrieval | `get_event_verification`, `get_incident_verification` | Reused; response is path-scrubbed |
| Safe UI and authorized evidence opening | `open_authorised_evidence`, typed `SafeUICommand` | Extended with a fixed incident-review route |
| Intent/context JSON chat | `aegis/ai/orchestrator.py` | Inspected only; not expanded into another agent |
| Persisted incident lookup, evidence metadata, timeline, trajectory, report | `aegis/intelligence/incident_investigation.py` | Added as read-only, agent-safe projections |
| On-demand VLM request | `aegis/ai/tools.py:analyze_incident_with_vlm` | Exposed through Live only via the existing Phase 1.7 privacy gate |
| Durable Live tool-call audit | `aegis/audit/service.py:record_audit` | Connected to every allow-listed Live tool call with free text omitted |

The Live tool allowlist is authoritative. No shell, arbitrary file, URL, or model-directed operational write tool is exposed by this extension.
