# Private automation roadmap

**Status:** Ordered backlog

Work is delivered as small end-to-end slices. A slice is complete only when its
code, contracts, tests, owner UI, metrics, alerts, runbook, and restart behavior
are verified together.

## Current status

| Slice | Status |
| --- | --- |
| 0. Runtime health foundation | Complete (2026-09-04) |
| 1. Durable execution skeleton | Complete (2026-09-04) |
| 2. Browser operations control plane | Planned |
| 3. Read-only reconnaissance | Planned |
| 4. Draft preparation | Planned |
| 5. Fenced submission | Planned |
| 6. Scale and orchestration review | Planned |

## Delivery order

### 0. Runtime health foundation

Goal: prove that the private runner can start, authenticate, report health, and
recover without any application capability.

- Dedicated LXD instance, persistent state, systemd supervision, and host boot.
- Separate NAT network with Kubernetes pod and service CIDRs rejected.
- Owner delegation and least-privilege M2M authentication.
- Deterministic API, database, Chrome, Playwright, Browser MCP, Job Hunter MCP,
  launcher, and Codex canary checks.
- Owner-only UI status, VictoriaMetrics series, dashboard, and actionable alerts.
- Controlled service and container restart drills.

Exit criteria: every component reports `READY`, heartbeat age remains within its
SLO, restart drills recover automatically, and a controlled outage fires and
resolves the expected alert.

Completion evidence:

- The exact automation revision is installed in a dedicated, autostarted LXD
  instance with a persistent Chrome profile and Codex authentication.
- Service and full-container restart drills recovered automatically with all
  eight required components returning to `READY`.
- The isolated runner network rejected Kubernetes pod and service CIDRs while
  the public API remained reachable.
- A controlled runner outage fired the stale-heartbeat warning, delivered its
  Telegram firing and resolved notifications without delivery errors, and
  returned all automation rules to `inactive` after recovery.
- The production dependency lock was checked against OSV and contains no known
  advisories at completion time.

### 1. Durable execution skeleton

Goal: establish recoverable work before adding real browser actions.

- API-owned run, work-item, lease, checkpoint, attempt, and event contracts with
  migrations.
- Stable idempotency keys, generation fencing, lease expiry, bounded retries, and
  an append-only audit event log. An external outbox remains deferred until a
  workflow has an external side effect.
- Runner claim, heartbeat, complete, fail, pause, and resume protocol.
- Owner UI for queue, active run, attempts, typed failures, and history.
- Restart tests at each transition, including process death after an API write and
  before the next step.

Exit criteria: a synthetic multi-step job survives API, runner, container, and
host restarts without losing progress or executing a completed step twice.

Completion evidence:

- API `v0.20.0` owns the PostgreSQL state machine, 60-second leases, three-attempt
  retry bound, generation fencing, owner and runner contracts, and database-backed
  workflow metrics.
- Automation revision `c3f26b1305f2cf73185be8d3421e8cff88a88311` runs the
  stateless synthetic worker. Service and full LXD restart drills resumed from the
  next incomplete checkpoint and completed exactly three unique steps.
- An API pod was replaced through GitOps while work was active; the run and lease
  remained available from PostgreSQL and completed after the runner resumed.
- Owner create, pause, resume, and stop controls were exercised in the production
  UI. Anonymous access returned `401`, the runner identity returned `403`, and
  wrong-owner denial is covered by integration tests.
- UI `v0.17.0` presents the actionable queue before diagnostics, polls live state
  every three to five seconds, separates history, and exposes attempts,
  checkpoints, integrity digests, and the audit timeline in a responsive owner
  report. Mobile navigation uses a compact header and temporary drawer instead of
  reserving a permanent rail. Synthetic runs explicitly show that no vacancy,
  browser session, screenshot, submission, or schedule exists.
- A controlled 15-minute stall fired `JobHunterAutomationWorkflowStalled` while
  the runner heartbeat remained fresh. Telegram delivery completed without an
  error; restoring normal execution completed both actionable runs, reduced queue
  and active metrics to zero, and resolved the alert.

### 2. Browser operations control plane

Goal: expose production-grade browser control without application submission.

- One persistent headed Chrome profile with serialized session ownership.
- Typed operations for navigate, observe, fill a non-sensitive fixture, upload a
  fixture, checkpoint, screenshot/evidence, and close.
- Allowed-domain and scheme validation, private-network rejection, timeouts,
  cancellation, rate limits, and artifact retention.
- Live owner view, current step, recent evidence, pause, resume, and stop controls.
- Run context that identifies the vacancy title, company, source, target URL, and
  trigger origin when a workflow is vacancy-related. Synthetic runs explicitly
  show that no vacancy is associated.
- Distinct scheduled, queued, active, and historical views with visible live-update
  freshness. Scheduling remains API-owned and appears only after its contract is
  implemented.
- Detailed owner reports for attempts, typed outcomes, checkpoints, audit events,
  screenshots, and retained browser evidence. Integrity hashes are not presented
  as screenshots.
- `WAITING_HUMAN` checkpoints for login, CAPTCHA, and ambiguous controls.

Exit criteria: fixture flows are deterministic, owner-visible, fully audited, and
resume only from server-owned checkpoints after every supported restart.

### 3. Read-only vacancy and application reconnaissance

Goal: resolve and classify application targets without writing to external sites.

- Resolve source links and redirects to a validated application target.
- Detect supported ATS/provider and form version.
- Inventory fields and required documents as untrusted structured data.
- Record unsupported, changed, challenged, and policy-quarantined outcomes.
- Report coverage and adapter drift by source and provider.

Exit criteria: no external form is modified and every eligible vacancy receives a
typed, reviewable reconnaissance result.

### 4. Draft preparation

Goal: prepare exact application manifests while keeping external submission off.

- Verified answer catalog and explicit unknown-answer inbox.
- Selected, versioned CV and message artifacts with hashes.
- Field mapping and validation against deterministic site/ATS adapters.
- Owner preview showing source, value origin, artifact version, and unresolved
  facts.
- Required cover letter results in a typed skip according to current policy.

Exit criteria: a complete immutable manifest can be reproduced and reviewed; no
submit capability exists in the runner.

### 5. Fenced application submission

Goal: enable one provider at a time behind an explicit owner policy.

- One-time API-issued submit fence bound to work item, manifest hash, lease,
  provider, target, and policy version.
- Deterministic adapter consumes the fence immediately before the irreversible
  click.
- Post-submit evidence and read-only reconciliation for ambiguous outcomes.
- No blind retry after a possible submission.
- Per-provider kill switch, anomaly circuit breaker, dashboards, alerts, and
  reports.

Exit criteria: duplicate-submission and ambiguous-result tests pass, a controlled
provider rollout is observable end to end, and revoking delegation stops new work.

### 6. Scale and orchestration review

Goal: decide from evidence whether the existing state machine remains sufficient.

- Measure queue depth, workflow duration, recovery complexity, retries,
  compensation needs, operator toil, and deployment/versioning friction.
- Write an ADR comparing the current design with Restate and Temporal.
- Add concurrency only after per-profile and per-provider safety limits exist.

Exit criteria: retain the current design or approve a bounded migration with data
ownership, rollback, and operational cost documented.

## Definition of done for every slice

- One owner-visible flow works end to end.
- Authorization and negative access tests cover owner, non-owner, M2M, and
  unauthenticated callers as applicable.
- Durable transitions are idempotent and fenced.
- Logs and metrics are redacted and bounded in cardinality.
- Alerts describe an operator action and have a verified resolution path.
- Service README, architecture, API contract, deployment, dashboard, runbook, and
  this backlog reflect shipped behavior.
- Focused checks and one full final verification pass.
- Conventional commits are merged, component gitlinks are updated, and production
  runs an exact recorded revision.

## Explicit non-goals

- Anti-detection guarantees, CAPTCHA solving, fingerprint spoofing, or
  access-control bypass.
- A microservice per source, ATS, agent, or browser tab.
- A second business database inside the automation runtime.
- Temporal or Restate before measured requirements justify the operational cost.
- Automatic submission before durable work, human checkpoints, evidence, and
  submit fencing are proven.
