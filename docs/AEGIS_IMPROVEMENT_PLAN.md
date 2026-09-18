# AegisAI improvement plan

Updated: 2026-09-16

## Direction

Prioritize a reliable, secure core with smarter alerts. Build on the existing
camera, detection, incident, and audit modules in small, verifiable increments.
The intended experience: an operator sees an important incident, understands
the supporting evidence, and can acknowledge or investigate it confidently.

## Initial evidence

- The dashboard backend proxy injects a server-side API credential without
  authenticating the dashboard caller. The frontend middleware handles locale
  routing and excludes API routes. Dashboard user authentication and permissions
  are the first access-control milestone before internet exposure. A backend
  API key alone does not authenticate a dashboard user.
- The backend exempts requests bearing its valid internal proxy signature from
  global rate limiting. Add appropriate limits at the authenticated dashboard
  boundary, especially for AI requests and mutations.
- Durable alerts, incident correlation, and audit code already exist. Extend
  these implementations instead of introducing parallel systems.
- The alert manager checks cooldown before generating an alert without comparing
  the new severity. Verify the full pipeline's handling of a worsening incident;
  a cooldown must not hide a meaningful escalation.
- Older status documents do not accurately describe all current modules. Use
  source inspection and test results as the baseline.

Focused baseline: **17 tests passed**, with **79 warnings**, across:

```text
tests/security/test_phase1_production_blockers.py
tests/unit/test_operational_alert_persistence.py
tests/unit/test_incident_correlation.py
tests/unit/test_phase3_operational_hardening.py
```

The test process used an in-memory default database; persistence tests supplied
their own temporary databases. This is a focused baseline, not a full security
audit or proof of live camera accuracy. Warnings remain to be triaged.

## Delivery order

| Increment | Result | Acceptance check |
| --- | --- | --- |
| 1. Dashboard access control | Authenticated sessions, viewer/operator/admin permissions, protected proxy and WebSocket token issuance, mutation protection, request limits | Signed-out callers cannot retrieve camera data or obtain socket tokens; forbidden actions are rejected server-side; expired sessions fail closed |
| 2. Trustworthy alerts | Evidence links, explicit uncertainty, repeated-event suppression, severity escalation, durable operator acknowledgement | Replay repeated observations and a worsening incident; verify duplicate suppression, escalation visibility, restart persistence, and audit records |
| 3. Evidence-based assistant | Answers about actual incidents with camera/time references and clear missing-data states | Known questions match stored evidence; unsupported conclusions are not presented as observed facts |
| 4. Operational resilience | Clear offline/stale states, recovery checks, tested backup restoration, retention policy | Exercise camera disconnect, service restart, unavailable optional services, and restoration without losing required incident history |

Select the intended deployment environment and identity mechanism before
implementing increment 1. Reuse a maintained authentication solution appropriate
to that environment. Keep authorization in server handlers, including the proxy
and token exchange; hiding a UI control is insufficient.

For increment 2, establish labeled replay scenarios and measure false alerts,
missed important events, and time to alert before changing detection thresholds.
Keep model confidence distinct from incident severity and human judgement.

## Cost-conscious working agreement

- One bounded change at a time, with its acceptance check stated up front.
- Read relevant modules and preserve the substantial existing uncommitted work.
- Use targeted checks; expand testing when the change crosses more boundaries.
- Keep updates brief and record durable decisions here.
- Reuse local detection and deterministic rules where sufficient. Reserve paid
  AI calls for useful summaries or difficult queries; define budgets and measure
  usage before enabling continuous AI analysis.
- Finish each increment with what changed, what passed, and what remains open.

## Next concrete task

Close the unauthenticated dashboard proxy boundary. Decide whether the first
deployment is a single-operator local installation or a shared hosted service,
then implement and verify the corresponding session and permission flow.
