# Durable Execution Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task by task.

**Goal:** Deliver an owner-only synthetic workflow that persists every state
transition in PostgreSQL, survives API and runner restarts, and never executes a
completed step twice.

**Architecture:** The Kotlin API and PostgreSQL remain the sole durable workflow
authority. The private automation service is a stateless lease worker that reports
its runner generation, checkpoints deterministic steps, and obeys API-owned
pause, resume, stop, retry, and stale-generation fencing. The existing owner-only
React route exposes controls and history. No external job site, browser mutation,
CAPTCHA handling, submission, or second workflow database is part of this slice.

**Tech stack:** Kotlin, Spring Boot, Spring Security, Spring Data JPA, Flyway,
PostgreSQL, Micrometer, TypeScript, Node.js, React, TanStack Query, Ant Design,
Vitest, Mock Service Worker, VictoriaMetrics, Prometheus rules, Grafana, Helm.

**Specification:** `docs/backlog/automation-roadmap.md`, slice 1.

## Global constraints

- Keep the API backward compatible while the worker and UI roll out.
- Do not add Restate, Temporal, a second database, or another runtime dependency.
- Use UUID idempotency keys, opaque lease tokens, monotonic runner generations,
  row locks for transitions, bounded payloads, and an append-only event log.
- Store only synthetic step names and SHA-256 evidence in this slice.
- Reject stale or expired leases before accepting any checkpoint or completion.
- Treat pause and stop as server-side lease invalidation. A stopped run cannot be
  resumed; a paused run can be resumed by its configured owner only.
- Keep all UI and owner APIs behind configured-owner plus automation scopes.
- Preserve the user-owned untracked `docs/ideas/` tree.

---

## Task 1: PostgreSQL workflow state machine

**Files:**

- Create: `api/src/main/resources/db/migration/V29__add_automation_workflows.sql`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/automation/workflow/AutomationWorkflowRunEntity.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/automation/workflow/AutomationWorkItemEntity.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/automation/workflow/AutomationWorkAttemptEntity.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/automation/workflow/AutomationWorkflowCheckpointEntity.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/automation/workflow/AutomationWorkflowEventEntity.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/automation/workflow/AutomationWorkflowStatus.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/automation/workflow/AutomationWorkItemStatus.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/automation/workflow/AutomationAttemptOutcome.kt`
- Create repositories in the same package for the five entities.
- Create: `api/src/test/kotlin/com/mshykhov/jobhunter/application/automation/workflow/AutomationWorkflowPersistenceIntegrationTest.kt`

- [ ] Write failing migration and persistence tests for one idempotent run, one
      work item, unique ordered checkpoints, attempts, and immutable events.
- [ ] Add normalized tables, foreign keys, status checks, unique constraints,
      lease indexes, and bounded text/JSON columns in Flyway V29.
- [ ] Implement JPA entities following the repository UUID/Persistable pattern.
- [ ] Run
      `JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home ./gradlew test --tests '*AutomationWorkflowPersistenceIntegrationTest'`
      and confirm it passes.
- [ ] Commit in `api/` as `feat(automation): add durable workflow persistence`.

## Task 2: Transactional workflow service and recovery invariants

**Files:**

- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/automation/workflow/AutomationWorkflowService.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/automation/workflow/AutomationWorkflowModels.kt`
- Create: `api/src/test/kotlin/com/mshykhov/jobhunter/application/automation/workflow/AutomationWorkflowServiceIntegrationTest.kt`
- Modify: `api/src/main/kotlin/com/mshykhov/jobhunter/application/automation/AutomationService.kt`

The service contract is:

```kotlin
fun createRun(delegationId: UUID, idempotencyKey: UUID): WorkflowRunView
fun claim(workerId: String, generation: Long): WorkClaim?
fun heartbeat(command: LeaseCommand): LeaseView
fun checkpoint(command: CheckpointCommand): WorkProgress
fun complete(command: LeaseCommand): WorkProgress
fun fail(command: FailureCommand): WorkProgress
fun pause(runId: UUID): WorkflowRunView
fun resume(runId: UUID): WorkflowRunView
fun stop(runId: UUID): WorkflowRunView
```

- [ ] First write failing integration tests for duplicate create/checkpoint,
      lease expiry, maximum three attempts, pause/resume/stop, and stale runner
      generation after `AutomationService.startSession()`.
- [ ] Implement three synthetic steps: `PREPARE`, `EXECUTE`, `VERIFY`.
- [ ] Make claim recover expired leases before selecting one queued item with a
      database lock; keep at most one active lease per work item.
- [ ] Make checkpoint idempotent by work item plus key and advance the stored
      step only after the unique checkpoint row exists.
- [ ] Invalidate active leases and close attempts when a newer runner generation
      starts, immediately requeueing resumable work.
- [ ] Append a bounded audit event inside the same transaction as every accepted
      transition. Defer an external outbox table until this workflow has an
      external side effect.
- [ ] Run the focused service suite on JDK 21 and commit as
      `feat(automation): implement durable workflow transitions`.

## Task 3: Owner and runner HTTP contracts

**Files:**

- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/automation/AutomationWorkflowController.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/automation/AutomationWorkflowRunnerController.kt`
- Create DTOs under `api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/automation/dto/workflow/`.
- Modify: `api/src/main/kotlin/com/mshykhov/jobhunter/infrastructure/security/SecurityConfig.kt`
- Create: `api/src/test/kotlin/com/mshykhov/jobhunter/api/rest/automation/AutomationWorkflowControllerIntegrationTest.kt`
- Create: `api/src/test/kotlin/com/mshykhov/jobhunter/api/rest/automation/AutomationWorkflowRunnerControllerIntegrationTest.kt`

Owner endpoints:

```text
POST /automation/workflows/runs
GET  /automation/workflows/runs
GET  /automation/workflows/runs/{runId}
POST /automation/workflows/runs/{runId}/pause
POST /automation/workflows/runs/{runId}/resume
POST /automation/workflows/runs/{runId}/stop
```

Runner endpoints:

```text
POST /automation/runner/work-items/claims
POST /automation/runner/work-items/{workItemId}/heartbeat
POST /automation/runner/work-items/{workItemId}/checkpoints
POST /automation/runner/work-items/{workItemId}/complete
POST /automation/runner/work-items/{workItemId}/fail
```

- [ ] Write failing MockMvc tests for owner, wrong owner, missing scope, runner
      M2M, regular user, malformed input, stale token, and idempotent replay.
- [ ] Implement bounded request validation and typed conflict/error responses.
- [ ] Extend security mappings without weakening `/automation/status` or runner
      health authorization.
- [ ] Run both new controller suites and the existing automation controller
      suites, then commit as `feat(automation): expose workflow control APIs`.

## Task 4: Metrics and API documentation

**Files:**

- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/infrastructure/metrics/AutomationWorkflowMetrics.kt`
- Create: `api/src/test/kotlin/com/mshykhov/jobhunter/infrastructure/metrics/AutomationWorkflowMetricsTest.kt`
- Modify: `api/README.md`

- [ ] Write failing tests for queue depth, active work, terminal failures, retry
      count, and oldest actionable work age with bounded labels only.
- [ ] Publish database-backed gauges/counters that recover after API restart.
- [ ] Document contracts, status semantics, fencing, retention, and synthetic-only
      scope in the API README.
- [ ] Run the metric tests and `./gradlew check` on JDK 21, then commit as
      `feat(automation): publish workflow metrics`.

## Task 5: Shared runner session and workflow API client

**Files:**

- Create: `automation/src/runner/session-coordinator.ts`
- Create: `automation/src/runner/__tests__/session-coordinator.test.ts`
- Modify: `automation/src/runner/heartbeat-loop.ts`
- Modify: `automation/src/runner/__tests__/heartbeat-loop.test.ts`
- Modify: `automation/src/api/job-hunter-client.ts`
- Modify: `automation/src/api/__tests__/job-hunter-client.test.ts`

- [ ] Write failing tests proving concurrent heartbeat/work calls share one
      generation and a stale-generation response refreshes it once.
- [ ] Extract session lifecycle from `HeartbeatLoop` into a serialized
      `RunnerSessionCoordinator` used by both loops.
- [ ] Add typed claim, heartbeat, checkpoint, complete, and fail client methods;
      preserve redaction and timeout behavior.
- [ ] Run the focused Vitest files and commit as
      `feat(runner): add durable workflow client`.

## Task 6: Synthetic lease worker

**Files:**

- Create: `automation/src/workflows/synthetic-workflow-worker.ts`
- Create: `automation/src/workflows/__tests__/synthetic-workflow-worker.test.ts`
- Modify: `automation/src/config.ts`
- Modify: `automation/src/__tests__/config.test.ts`
- Modify: `automation/src/launcher.ts`
- Modify: `automation/src/__tests__/launcher.test.ts`
- Modify: `automation/README.md`
- Modify: `automation/deploy/systemd/job-hunter-automation.env.example`

- [ ] Write failing tests for normal completion, response loss after checkpoint,
      pause/stop control, lease loss, stale generation, bounded retry, graceful
      shutdown, and resume at the next incomplete step.
- [ ] Execute deterministic local step functions only and hash bounded evidence.
- [ ] Poll through the shared session coordinator and stop processing immediately
      when the API revokes a lease.
- [ ] Add disabled-by-default worker configuration and document production values.
- [ ] Run focused tests, then `npm run verify`, and commit as
      `feat(runner): execute synthetic recoverable workflows`.

## Task 7: Owner-only workflow UI

**Files:**

- Modify: `ui/src/constants/api.ts`
- Modify: `ui/src/features/automation/types.ts`
- Create: `ui/src/features/automation/hooks/useAutomationWorkflows.ts`
- Create: `ui/src/features/automation/components/AutomationWorkflowPanel.tsx`
- Create: `ui/src/features/automation/components/__tests__/AutomationWorkflowPanel.test.tsx`
- Modify: `ui/src/features/automation/components/AutomationPage.tsx`
- Modify: `ui/src/features/automation/components/__tests__/AutomationPage.test.tsx`
- Modify: `ui/src/mocks/automationFixture.ts`
- Modify: `ui/README.md`

- [ ] Write failing UI tests for queue/history rendering, attempt/checkpoint
      details, typed failures, create, pause, resume, stop, read-only scope, and
      owner route protection.
- [ ] Add TanStack queries/mutations through the shared API client only.
- [ ] Render one compact responsive control panel inside the existing owner route.
- [ ] Verify desktop and 390x844 layouts in a browser, capture any accessibility
      regressions, and run the full UI check.
- [ ] Because the repository-required `release-ui` skill is unavailable in this
      session, use the repository's documented version/release commands as the
      explicit fallback.
- [ ] Commit as `feat(automation): add durable workflow controls`.

## Task 8: Alert, dashboard, and infrastructure tests

**Files:**

- Modify: `/Users/myron/IdeaProjects/smhomelab-infrastructure/manifests/monitoring/prometheus-rules/job-hunter-alerts.yaml`
- Modify: `/Users/myron/IdeaProjects/smhomelab-infrastructure/tests/prometheus/job-hunter-automation.test.yaml`
- Modify: `/Users/myron/IdeaProjects/smhomelab-infrastructure/charts/grafana-dashboards/dashboards/applications/job-hunter-automation.json`
- Create: `/Users/myron/IdeaProjects/smhomelab-infrastructure/docs/plan/000067-PLAN-job-hunter-durable-execution.md`

- [ ] Read the infrastructure repository instructions before editing.
- [ ] First add failing rule tests for actionable work stalled over 15 minutes
      and for correct resolution after progress.
- [ ] Add a low-cardinality alert with an operator runbook annotation and panels
      for queue, active work, retry/failure totals, progress age, and outcomes.
- [ ] Render/validate the rule and dashboard, run the focused Prometheus test and
      infrastructure CI-equivalent checks.
- [ ] Commit and merge a conventional infrastructure PR.

## Task 9: Release, production recovery drills, and documentation closure

**Files:**

- Modify API/UI versions only through their documented release mechanisms.
- Modify: `/Users/myron/IdeaProjects/smhomelab-deploy/services/job-hunter-api/values-prd.yaml`
- Modify: `/Users/myron/IdeaProjects/smhomelab-deploy/services/job-hunter-ui/values-prd.yaml`
- Modify: `docs/architecture/service-boundaries.md`
- Modify: `docs/backlog/automation-roadmap.md`
- Modify: `README.md` only if navigation changes.
- Update root submodule gitlinks for `api/`, `automation/`, and `ui/`.

- [ ] Read deployment repository instructions, then deploy API before enabling
      the worker, deploy automation, and deploy UI last.
- [ ] Create a synthetic run and stop the runner after the first checkpoint.
      Confirm restart completes exactly three unique checkpoints and the old
      generation cannot write.
- [ ] Repeat across a full LXD container restart and an API pod restart.
- [ ] Exercise owner create/pause/resume/stop in the live UI and prove anonymous,
      non-owner, and runner identities cannot access owner endpoints.
- [ ] Fire and resolve the stalled-work alert in a controlled drill and verify
      notification delivery without exposing identifiers.
- [ ] Record exact revisions, test evidence, status semantics, restart behavior,
      operational commands, and remaining slices in architecture and backlog.
- [ ] Run component-focused checks, one final full verification pass, Rulesync
      verification, and documentation drift checks.
- [ ] Merge component PRs, update and merge root gitlinks/docs, and confirm
      production runs the recorded revisions with all repositories clean except
      the preserved user-owned `docs/ideas/` directory.
