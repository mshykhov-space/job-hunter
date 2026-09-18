# Service boundaries

**Status:** Accepted current architecture

Job Hunter is a system of independently deployable components coordinated by this
repository. Each component has one primary responsibility and one source of
truth. Cross-component behavior uses versioned API contracts rather than shared
databases, copied business logic, or direct access to another service's runtime.

## System flow

```text
vacancy sources
      |
      v
 Kotlin scraper -------------------> JobSpy sidecar (LinkedIn only)
      |
      | claims, heartbeats, normalized batches,
      | checkpoints, completion, and failure
      v
 Kotlin API  <------------------- private automation runtime
      |                              | health, claims, heartbeats,
      |                              | results, and evidence only
      v                              |
 PostgreSQL -------------------------+
      |
      +----------> Telegram
      |
      +----------> React UI
```

The Kotlin scraper is the target ingestion runtime, but it is disabled until
production acceptance and per-source cutover. Existing n8n workflows remain the
temporary ingestion owner for sources that have not cut over. A source must never
be active in both runtimes.

The API is the only business-state boundary. The automation runtime never reads
PostgreSQL, Kubernetes services, Vault, or VictoriaMetrics directly. Its network
allows public HTTPS APIs and rejects the Kubernetes pod and service CIDRs.

## Ownership

| Component | Owns | Must not own |
| --- | --- | --- |
| Kotlin scraper | Source adapters, bounded extraction, page traversal, lease heartbeats, and normalized batch delivery | Durable schedules, checkpoints, retry state, vacancy persistence, matching policy, or a service database |
| JobSpy sidecar | LinkedIn extraction behind the scraper's private runtime boundary | Scheduling, API credentials, durable state, or non-LinkedIn sources |
| `n8n/` | Temporary legacy extraction and delivery for sources not yet cut over | A source already enabled in the Kotlin scraper, matching policy, application workflow state, browser sessions, or user authorization |
| `api/` | Domain rules, PostgreSQL persistence, deduplication, matching, scraper schedules, fenced leases, criteria snapshots, checkpoints, idempotent batch receipts, audit events, Telegram delivery, and automation authorization | Source HTTP extraction, browser processes, persistent browser profiles, or Codex credentials |
| `ui/` | Authenticated operator experience, queries, commands, status, reports, and human checkpoints | Durable workflow decisions, direct database access, or hidden background orchestration |
| `automation/` | Bounded process execution, deterministic probes, browser control, protected local capability credentials, and ephemeral execution context | Business workflow state, schedules, policy, audit authority, or a second application database |
| Infrastructure repository | GitOps deployment, environment and secret delivery, JobSpy sidecar wiring, network policy, trace export configuration, dashboards, alerts, backups, and recovery procedures | Application policy or business workflow transitions |

Source adapters remain modules inside the scraper. ATS and application adapters
remain behind the automation runtime contract. An adapter becomes another
deployable unit only when isolation, scaling, or release cadence provides a
measured reason.

## Dependency rules

1. The scraper claims due work from the API and submits normalized vacancies in
   idempotent batches. It advances a checkpoint only after the final batch for a
   page is acknowledged.
2. UI and Telegram consume API-owned state and commands.
3. Automation obtains short-lived M2M tokens, then uses only explicit API and MCP
   capabilities bound to the configured owner.
4. The API validates owner delegation, leases, generations, sequence numbers,
   idempotency keys, and irreversible-action fences.
5. Services never share tables or reach into another service's container.
6. Contracts are versioned at the boundary and deployed compatibly before a
   caller starts using them.
7. GitOps enables scraper sources explicitly. The default source allowlist is
   empty, and a corresponding n8n schedule is stopped before a source is enabled.

These rules keep dependencies directed and support SOLID, DRY, and YAGNI:
business policy has one owner, execution adapters have narrow interfaces, and new
infrastructure is added only for a demonstrated requirement.

## State and restart model

| State | Source of truth | Restart behavior |
| --- | --- | --- |
| Vacancies, matching, preferences, scraper schedules, scrape runs, criteria snapshots, checkpoints, batch receipts, workflow runs, work items, leases, fences, audit, and reports | API and PostgreSQL | Reconstructed from PostgreSQL; expired leases are reclaimed through explicit bounded policy |
| Source page traversal, HTTP clients, and batch assembly | Scraper process | Discarded; the next claim resumes from the API-owned checkpoint and repeats acknowledged batches safely |
| Runner generation, heartbeat sequence, component snapshots, and delegation | API and PostgreSQL | A restarted runner opens a new fenced session; stale generations cannot write |
| Browser profile and interactive login session | Dedicated LXD state volume | Preserved across service and container restarts; validity is checked before work |
| Codex CLI credentials | Dedicated runner state with mode `0600` | Preserved across ephemeral runs; authentication failure becomes a typed health state |
| In-memory timers, page handles, and process context | Automation process | Discarded; a restart resumes only from the next API-owned checkpoint |

The LXD instance starts with the host and systemd restarts the service on failure.
The shipped synthetic recovery contract is resumable because every accepted step is
checkpointed in PostgreSQL before the next step begins. This does not make an
arbitrary browser click resumable. Real browser and application operations still
require typed API-owned checkpoints, evidence, and irreversible-action fences; the
runtime cannot submit applications.

## Deployment and observability

The infrastructure repository is the deployment source of truth. GitOps supplies
environment-specific endpoints, source allowlists, resource limits, and secret
references; application repositories contain no environment credentials. The
scraper uses a scoped machine identity for the API and runs JobSpy as a private
LinkedIn-only sidecar.

The API exposes durable per-source success, failure, enablement, and volume
metrics. Scraper and API traces go directly over OTLP/HTTP to the existing
VictoriaTraces endpoint with bounded export timeouts; no collector or trace-backed
business state is introduced. Source enablement, freshness alerts, logs, and
stored traces must be observed before an n8n workflow is retired.

## Durable synthetic workflow

The first durable slice implements one intentionally bounded workflow type:
`SYNTHETIC_RECOVERY`.

```text
owner UI -> create run -> API/PostgreSQL queue -> stateless LXD worker
                                      ^                  |
                                      +-- lease/checkpoint+
```

- One run owns one work item and the ordered `PREPARE`, `EXECUTE`, and `VERIFY`
  checkpoints.
- A claim creates a 60-second lease and an attempt bound to the current runner
  generation. A new session fences the old generation and requeues unfinished work.
- Checkpoint UUIDs make response replay idempotent; the unique step index prevents a
  completed step from being recorded twice.
- Pause revokes the lease and can be resumed. Stop revokes the lease and is terminal.
- Every accepted transition writes a bounded append-only event in the same database
  transaction. No outbox exists yet because this synthetic workflow has no external
  side effect.
- The worker has no workflow database. Process-local timers and execution context are
  disposable and reconstructed from the next incomplete API-owned checkpoint.

Owner endpoints require `read:automation` or `write:automation` and are additionally
bound to the configured immutable owner issuer and subject. The runner M2M identity
can operate only runner endpoints; it cannot read or control owner workflows.

## Security and privacy

- Owner-facing automation controls and status are available only to the
  configured owner.
- The M2M identity is a machine capability, not a user session, and cannot enable
  its own delegation or change schedules and policy.
- Secrets, cookies, OAuth files, and form values do not enter metrics or ordinary
  logs.
- Website content is untrusted data and cannot change tool permissions, policy,
  destinations, or instructions.
- CAPTCHA and authentication challenges become `WAITING_HUMAN` checkpoints.
  The system does not bypass access controls, fingerprinting defenses, or site
  prohibitions.
- Interaction pacing, bounded retries, and cooldowns are deterministic operational
  policy, not an attempt to conceal automation.
- Irreversible submission requires an API-issued one-time fence immediately before
  the action. An ambiguous result is reconciled, never retried blindly.

## Orchestration decision

The current choice is a PostgreSQL-backed state machine in the API plus a thin
systemd-supervised runner. Restate or Temporal is not a current dependency.

Create an ADR and evaluate a workflow engine only when production evidence shows
at least one of these needs cannot be kept simple in the existing boundary:

- many concurrent workflows with long timers and complex recovery;
- cross-service compensation or child-workflow semantics;
- safe workflow-code versioning across long-lived executions;
- operational visibility that cannot be delivered from the existing audit,
  status, metrics, and reports;
- repeated correctness failures in the lease, checkpoint, or retry model.

The ADR must compare migration cost, operational burden, data ownership, failure
modes, and rollback. A workflow engine may coordinate execution, but PostgreSQL
remains the business record unless a separate migration is explicitly approved.

## Legacy removal rule

The dedicated n8n ingestion repository and gitlink remain during migration. Retire
them only after every source has passed live acceptance, the Kotlin scraper is the
sole enabled ingestion owner, API source metrics are fresh, traces are stored, and
rollback revisions are recorded. This document does not claim that production
cutover is complete.

Legacy code can be removed after all real consumers are identified, replacement
contracts are deployed, data migration or retention is complete, observability
shows no remaining use, and rollback is documented. Do not keep compatibility
layers, commented-out paths, or temporary dual writes without a dated removal
criterion.
