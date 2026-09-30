# AegisAI presentation: critical questions and defensible answers

Use these as speaking notes. Replace any performance or accuracy statement with a measurement from the exact demo build and hardware.

## Opening answer (45–60 seconds)

**What is AegisAI?** AegisAI helps an operator review camera activity. It detects and tracks objects, combines observations over time into contextual risk signals, records supporting evidence, and presents alerts in a live dashboard. The operator verifies the scene and decides what to do. The prototype demonstrates the data flow; field accuracy and scale still require formal evaluation.

## Questions from evaluators and engineers

1. **How does this differ from running YOLO on a video?** YOLO supplies object observations. AegisAI adds tracking, contextual risk rules, event persistence, alert delivery, evidence search, and an operator workflow. Show one event moving through those stages.
2. **Why choose lightweight YOLO and ByteTrack?** They offer a practical latency and resource tradeoff for the local processing path. Compare alternatives on the same footage and hardware before claiming one is best.
3. **What does a risk score mean?** It prioritizes review based on observed factors such as detections, proximity, persistence, and context. It is not a probability that a person will commit a crime. Show the factors and supporting frame.
4. **How were risk weights and thresholds selected?** They are configurable engineering parameters. Before deployment, tune them against annotated footage from the intended environment and publish the tradeoff between misses and false alerts.
5. **What is your detection precision and recall?** We do not have a defensible field number yet. The local evaluation set has only two unique unlabeled clips. Independent labeling and held-out testing are next.
6. **What about false alarms from phones, tools, or shadows?** Those are hard negatives to include in evaluation. Temporal and contextual checks may reduce one-frame alerts, but their effect must be measured.
7. **What about missed threats?** Camera angle, lighting, occlusion, image quality, and model limitations can cause misses. The system assists monitoring. Report recall by scenario when validated.
8. **Is the system real-time?** System latency depends on hardware, stream count, frame size, buffering, and network conditions. Report camera-to-screen p50/p95 latency for the demo setup; model FPS alone is insufficient.
9. **Can it handle 100 cameras?** That has not been demonstrated. Partition camera processing across workers or edge nodes and load-test event delivery, storage, and subscriptions before promising capacity.
10. **What happens when a camera or optional AI service fails?** Health endpoints and the UI expose availability; optional features may be unavailable. Demonstrate disconnect and recovery. A reliability claim needs fault-injection and soak tests.
11. **Why use SQLite locally and PostgreSQL for deployment?** SQLite keeps the local demo simple. PostgreSQL is the intended multi-user persistence path. A clean initial migration and upgrade/recovery tests remain necessary.
12. **How are video and evidence protected?** Protected API routes use a server-held key and WebSocket access checks. Production needs operator identity, roles, evidence access audit, and retention policy.
13. **Does it identify people across cameras or recognize faces?** Neither is a demonstrated core capability. The current tracking flow follows objects within camera streams. Cross-camera identity would need separate validation and governance.
14. **What role does Gemini play?** It supports optional natural-language and voice interaction with system data. Detection and basic risk processing do not depend on a Gemini key. AI responses should be checked against the referenced evidence.
15. **What is actually original here?** The contribution is the integrated operator workflow and contextual use of observations, evidence, alerts, and explanations. General-purpose models and web frameworks are established technologies.
16. **Why should we trust your demo?** We can show the live data path, health state, saved evidence, and reproducible test commands. The demo proves that flow, while field accuracy and reliability still need measurements.
17. **What is the first production blocker you would fix?** Complete the database migration path and operator identity/access controls, then establish release gates for accuracy, latency, and failure recovery.

## Demo sequence and backup

1. Run `python scripts/demo_preflight.py` with the local API key; capture the readiness output.
2. Connect one known camera or consented clip. Show its source and live status.
3. Follow one observation to a track, contextual assessment, saved event, and dashboard alert. Open the supporting evidence.
4. Show what the operator sees when evidence is missing or a service is unavailable.
5. Keep a recorded walkthrough and saved example event ready if the live source fails. Label recorded material clearly.

## Numbers to bring to the presentation

Record the device CPU/GPU, model checkpoint, input resolution, number of streams, tested clip count, p50/p95 camera-to-alert latency, false alerts per camera-hour, precision/recall (only on labeled independent data), and the exact commit tested. Use “not yet measured” for any missing value.
