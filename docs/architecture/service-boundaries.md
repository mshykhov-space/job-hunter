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
 n8n scraping workflows
      |
      | normalized REST payloads
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

The API is the only business-state boundary. The automation runtime never reads
PostgreSQL, Kubernetes services, Vault, or VictoriaMetrics directly. Its network
allows public HTTPS APIs and rejects the Kubernetes pod and service CIDRs.

## Ownership

| Component | Owns | Must not own |
| --- | --- | --- |
| `n8n/` | Source schedules, scraping workflows, extraction, and normalized vacancy delivery | Matching policy, application workflow state, browser sessions, or user authorization |
| `api/` | Domain rules, PostgreSQL persistence, deduplication, matching, schedules, leases, idempotency, submit fences, audit/outbox, Telegram delivery, and automation authorization | Browser processes, persistent browser profiles, or Codex credentials |
| `ui/` | Authenticated operator experience, queries, commands, status, reports, and human checkpoints | Durable workflow decisions, direct database access, or hidden background orchestration |
| `automation/` | Bounded process execution, deterministic probes, browser control, protected local capability credentials, and ephemeral execution context | Business workflow state, schedules, policy, audit authority, or a second application database |
| Infrastructure repository | Kubernetes and LXD deployment, secrets delivery, network policy, dashboards, alerts, backups, and recovery procedures | Application policy or business workflow transitions |

Logical source and ATS adapters live behind the automation runtime contract. They
do not become separate microservices until isolation, scaling, or release cadence
provides a measured reason for another deployable unit.

## Dependency rules

1. Scrapers submit normalized vacancies to the API.
2. UI and Telegram consume API-owned state and commands.
3. Automation obtains short-lived M2M tokens, then uses only explicit API and MCP
   capabilities bound to the configured owner.
4. The API validates owner delegation, leases, generations, sequence numbers,
   idempotency keys, and irreversible-action fences.
5. Services never share tables or reach into another service's container.
6. Contracts are versioned at the boundary and deployed compatibly before a
   caller starts using them.

These rules keep dependencies directed and support SOLID, DRY, and YAGNI:
business policy has one owner, execution adapters have narrow interfaces, and new
infrastructure is added only for a demonstrated requirement.

## State and restart model

| State | Source of truth | Restart behavior |
| --- | --- | --- |
| Vacancies, matching, preferences, schedules, workflow runs, work items, leases, fences, audit, and reports | API and PostgreSQL | Reconstructed from PostgreSQL; expired leases are reclaimed through explicit policy |
| Runner generation, heartbeat sequence, component snapshots, and delegation | API and PostgreSQL | A restarted runner opens a new fenced session; stale generations cannot write |
| Browser profile and interactive login session | Dedicated LXD state volume | Preserved across service and container restarts; validity is checked before work |
| Codex CLI credentials | Dedicated runner state with mode `0600` | Preserved across ephemeral runs; authentication failure becomes a typed health state |
| In-memory timers, page handles, and process context | Automation process | Discarded; a restart resumes only from the next API-owned checkpoint |

The LXD instance starts with the host and systemd restarts the service on failure.
This does not make an arbitrary browser click resumable. Durable browser and
application operations require API-owned step checkpoints, leases, and fences.
Until that contract is implemented, the runtime performs health checks only and
cannot submit applications.

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

Legacy code can be removed after all real consumers are identified, replacement
contracts are deployed, data migration or retention is complete, observability
shows no remaining use, and rollback is documented. Do not keep compatibility
layers, commented-out paths, or temporary dual writes without a dated removal
criterion.
