# Runtime Memory and Observability Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate the Job Hunter preference-save OOM path, make JVM heap sizing effective for every managed JVM workload, restore application-to-VictoriaTraces OTLP traffic, and alert on the failure modes that the 2026-08-10 incident exposed.

**Architecture:** Preference changes remain transactional events, but a dedicated single-thread executor runs retro filtering after commit. The worker snapshots lightweight group IDs, loads the existing entity graph in bounded chunks, deletes rejected rows in batches, and clears persistence state between chunks. Deployment configuration uses the JVM-native `JAVA_TOOL_OPTIONS`; shared monitoring adds a narrowly scoped trace-ingress policy plus heap, restart, matching-stall, and trace-ingestion alerts.

**Tech Stack:** Kotlin 2.1, Spring Boot 3.5, Spring Data JPA, MockK/JUnit 5, Gradle, Helm, Kubernetes NetworkPolicy, PrometheusRule/VictoriaMetrics, Argo CD.

**Design:** `docs/superpowers/specs/2026-08-10-runtime-memory-observability-design.md`

---

## Task 1: Create isolated deploy workspace and capture baselines

**Files:**
- Inspect: `/Users/myron/IdeaProjects/smhomelab-deploy/.gitignore`
- Inspect: `/Users/myron/IdeaProjects/smhomelab-deploy/CLAUDE.md`
- Inspect: `/Users/myron/IdeaProjects/job-hunter/api/AGENTS.md`
- Inspect: `/Users/myron/IdeaProjects/smhomelab-infrastructure/AGENTS.md`

**Step 1: Confirm repository state and upstreams**

Run:

```sh
git -C /Users/myron/IdeaProjects/job-hunter status --short --branch
git -C /Users/myron/IdeaProjects/job-hunter/api status --short --branch
git -C /Users/myron/IdeaProjects/smhomelab-deploy status --short --branch
git -C /Users/myron/IdeaProjects/smhomelab-infrastructure status --short --branch
```

Expected: Job Hunter, API, and infrastructure are clean; deploy may contain the user's unrelated `.gitignore`, `CLAUDE.md`, and plan changes.

**Step 2: Create a deploy worktree without touching the dirty checkout**

Use the repository preference if documented. Otherwise use:

```sh
git -C /Users/myron/IdeaProjects/smhomelab-deploy fetch origin master
git -C /Users/myron/IdeaProjects/smhomelab-deploy worktree add \
  "$HOME/.config/superpowers/worktrees/smhomelab-deploy/runtime-memory-observability" \
  -b fix/runtime-memory-observability origin/master
```

Expected: an isolated clean worktree on `fix/runtime-memory-observability`; the original checkout remains byte-for-byte untouched.

**Step 3: Record live incident baselines**

Run read-only checks for current pod restarts, heap flags, trace reachability, and alert-rule health. Save results in the eventual PSA, not as generated repository artifacts.

```sh
kubectl get pods -A -o wide
kubectl -n job-hunter-prd get pod -l app.kubernetes.io/name=job-hunter-api -o yaml
kubectl -n monitoring get prometheusrules
kubectl -n monitoring get pod -l app.kubernetes.io/instance=victoria-traces --show-labels
```

Expected: API effective heap is 256 MiB before deploy correction; VictoriaTraces is healthy but blocked from the application namespace.

---

## Task 2: Add failing regression tests for bounded retro filtering

**Files:**
- Modify: `api/src/test/kotlin/com/mshykhov/jobhunter/application/matching/ColdFilterRetroServiceTest.kt`
- Create: `api/src/test/kotlin/com/mshykhov/jobhunter/infrastructure/config/AsyncConfigTest.kt`

**Step 1: Rewrite service test fixtures around ID-first batching**

Construct the service with an `EntityManager` mock. Replace old full-history stubs with:

```kotlin
every { userJobGroupFacade.findIdsByUserIdAndStatus(user.id, UserJobStatus.NEW) } returns ids
every { userJobGroupFacade.findByIdsWithGroupAndJobs(chunk) } returns groups
every { userJobGroupFacade.deleteAllInBatch(any()) } just Runs
every { userJobGroupFacade.flush() } just Runs
every { entityManager.clear() } just Runs
```

Preserve tests for cold-filter semantics and longest-description representative selection.

**Step 2: Add the bounded-chunk regression**

Add a test with `BATCH_SIZE + 1` identifiers. Capture calls to `findByIdsWithGroupAndJobs` and assert:

```kotlin
assertEquals(listOf(BATCH_SIZE, 1), fetchedChunks.map(List<UUID>::size))
verify(exactly = 2) { userJobGroupFacade.flush() }
verify(exactly = 2) { entityManager.clear() }
```

The fixture can return passing empty-job groups so deletion volume does not obscure fetch boundaries.

**Step 3: Add executor contract test**

Instantiate `AsyncConfig`, retrieve `coldFilterRetroExecutor`, and assert one core thread, one maximum thread, a bounded queue, and the expected thread prefix.

**Step 4: Run focused tests and confirm RED**

Run:

```sh
cd /Users/myron/IdeaProjects/job-hunter/api
./gradlew test --tests '*ColdFilterRetroServiceTest' --tests '*AsyncConfigTest'
```

Expected: compilation/test failures because batching methods, `AsyncConfig`, and persistence-context handling do not exist yet.

---

## Task 3: Implement bounded asynchronous retro filtering

**Files:**
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/infrastructure/config/AsyncConfig.kt`
- Modify: `api/src/main/kotlin/com/mshykhov/jobhunter/application/userjob/UserJobGroupRepository.kt`
- Modify: `api/src/main/kotlin/com/mshykhov/jobhunter/application/userjob/UserJobGroupFacade.kt`
- Modify: `api/src/main/kotlin/com/mshykhov/jobhunter/application/matching/ColdFilterRetroService.kt`
- Modify: `api/docs/job-matching-architecture.md`

**Step 1: Add the dedicated bounded executor**

Create an infrastructure bean equivalent to:

```kotlin
@Configuration
@EnableAsync
class AsyncConfig {
    @Bean(COLD_FILTER_RETRO_EXECUTOR)
    fun coldFilterRetroExecutor(): Executor =
        ThreadPoolTaskExecutor().apply {
            corePoolSize = 1
            maxPoolSize = 1
            queueCapacity = 16
            setThreadNamePrefix("cold-filter-retro-")
            initialize()
        }

    companion object {
        const val COLD_FILTER_RETRO_EXECUTOR = "coldFilterRetroExecutor"
    }
}
```

Keep this separate from scheduled-job configuration.

**Step 2: Add lightweight ID and bounded graph queries**

Add repository methods:

```kotlin
@Query("SELECT ujg.id FROM UserJobGroupEntity ujg WHERE ujg.user.id = :userId AND ujg.status = :status ORDER BY ujg.id")
fun findIdsByUserIdAndStatus(userId: UUID, status: UserJobStatus): List<UUID>

@EntityGraph(attributePaths = ["group", "group.jobs"])
@Query("SELECT DISTINCT ujg FROM UserJobGroupEntity ujg WHERE ujg.id IN :ids")
fun findByIdInWithGroupAndJobs(ids: List<UUID>): List<UserJobGroupEntity>
```

Expose thin facade methods with matching names plus transactional `deleteAllInBatch` and `flush` wrappers. Do not change the existing query used by unrelated flows unless proven unused.

**Step 3: Make the post-commit listener asynchronous and bounded**

Annotate the listener with:

```kotlin
@Async(AsyncConfig.COLD_FILTER_RETRO_EXECUTOR)
@TransactionalEventListener
@Transactional(propagation = Propagation.REQUIRES_NEW)
```

Load preferences and the ID snapshot first. For `ids.chunked(BATCH_SIZE)`, fetch only that graph, retain the existing longest-description evaluation, delete rejected groups via `deleteAllInBatch`, flush, then `EntityManager.clear()` in `finally` so each processed chunk releases managed entities. Log a completion summary. Catch failures only to log the user ID and rethrow so Spring's async exception handler sees them.

Use a small fixed constant such as:

```kotlin
internal const val COLD_FILTER_RETRO_BATCH_SIZE = 100
```

**Step 4: Run focused tests and confirm GREEN**

Run:

```sh
./gradlew test --tests '*ColdFilterRetroServiceTest' --tests '*AsyncConfigTest'
```

Expected: all focused tests pass.

**Step 5: Format and run all API verification**

Run:

```sh
./gradlew ktlintFormat
./gradlew build
npm run rulesync:verify
docker build -t job-hunter-api:runtime-memory-test .
```

Expected: formatting, unit/integration tests, Rulesync verification, and image build all pass.

**Step 6: Update matching architecture documentation**

Document that `PreferenceChangedEvent` returns independently of cleanup, execution is single-worker and bounded, entity graphs are loaded in chunks, and failures are logged without rolling back saved preferences.

**Step 7: Commit and push the API change**

```sh
git add src/main src/test docs/job-matching-architecture.md
git commit -m "fix(matching): bound retroactive preference filtering"
git push origin master
```

Expected: the API commit is upstream before the parent gitlink is updated.

---

## Task 4: Standardize heap configuration for every JVM workload

**Files (isolated deploy worktree):**
- Modify: `services/job-hunter-api/values.yaml`
- Modify: `services/email-watcher/values.yaml`
- Modify: `services/telegram-user-monitor/values.yaml`

**Step 1: Add a configuration regression check**

Run before editing:

```sh
rg -n 'name: JAVA_OPTS|name: JAVA_TOOL_OPTIONS' services
```

Expected: exactly three managed JVM services use `JAVA_OPTS` and none use `JAVA_TOOL_OPTIONS`.

**Step 2: Use the JVM-native environment variable**

Change only the environment-variable key in all three values files:

```yaml
- name: JAVA_TOOL_OPTIONS
  value: "-XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0"
```

Do not change memory requests/limits in this task.

**Step 3: Render every affected chart**

For each service run `helm dependency build`, `helm lint`, and both configured `helm template` variants using its base and environment values. Assert the rendered Deployment contains `JAVA_TOOL_OPTIONS` and no `JAVA_OPTS`.

Expected: all charts lint/render successfully and the environment rename is the only material deployment diff.

**Step 4: Commit and push without touching the user's dirty checkout**

```sh
git add services/job-hunter-api/values.yaml services/email-watcher/values.yaml services/telegram-user-monitor/values.yaml
git commit -m "fix(jvm): apply container heap sizing consistently"
git push origin HEAD:master
```

Expected: fast-forward push; original deploy checkout keeps all pre-existing user changes.

---

## Task 5: Restore trace ingress and add shared failure-mode alerts

**Files:**
- Modify: `/Users/myron/IdeaProjects/smhomelab-infrastructure/manifests/core/network-policies/monitoring.yaml`
- Modify: `/Users/myron/IdeaProjects/smhomelab-infrastructure/manifests/monitoring/prometheus-rules/oom-alerts.yaml`
- Modify: `/Users/myron/IdeaProjects/smhomelab-infrastructure/manifests/monitoring/prometheus-rules/job-hunter-alerts.yaml`
- Modify: `/Users/myron/IdeaProjects/smhomelab-infrastructure/manifests/monitoring/prometheus-rules/platform-alerts.yaml`

**Step 1: Confirm live selectors and metric labels**

Run read-only queries against Kubernetes and VictoriaMetrics to verify VictoriaTraces pod labels, the `tier=application` namespace label, JVM metric labels, restart counters, Job Hunter matching counters, and exact `vt_rows_ingested_total` type value.

Expected: selectors match current live objects and each PromQL expression is based on an existing series or intentionally uses an absence-safe `or vector(0)` guard.

**Step 2: Add narrow VictoriaTraces ingress**

Append a separate NetworkPolicy document selecting only the live VictoriaTraces labels and permitting only TCP 10428 from:

```yaml
namespaceSelector:
  matchLabels:
    tier: application
```

Keep the existing namespace-wide policy intact.

**Step 3: Add JVM heap and single-restart alerts**

In `oom-alerts.yaml` add:

- `JVMHeapNearLimit` warning when production heap used/max exceeds 85% for 10 minutes;
- `ContainerRestarted` warning for any increase over 15 minutes in a non-dev application container, while retaining `FrequentContainerRestarts` for sustained churn.

Use aggregation that avoids duplicate scrape series and excludes empty/POD infrastructure containers.

**Step 4: Add matching-stalled detection**

In `job-hunter-alerts.yaml`, alert when `jobhunter_matching_backlog > 0` while total matching evaluations do not advance for 30 minutes, with a hold time long enough to avoid a transient cold-filter-only cycle.

**Step 5: Add VictoriaTraces no-ingestion detection**

In `platform-alerts.yaml`, alert when `up{job="victoria-traces"} == 1` but OTLP protobuf rows do not increase for 30 minutes. Preserve the distinction between target-down and target-up-but-no-data.

**Step 6: Validate YAML, Kubernetes objects, and PromQL**

Run repository validation commands plus:

```sh
kubectl apply --dry-run=client -f manifests/core/network-policies/monitoring.yaml
kubectl apply --dry-run=client -f manifests/monitoring/prometheus-rules/oom-alerts.yaml
kubectl apply --dry-run=client -f manifests/monitoring/prometheus-rules/job-hunter-alerts.yaml
kubectl apply --dry-run=client -f manifests/monitoring/prometheus-rules/platform-alerts.yaml
```

Submit each final expression to the live VictoriaMetrics query API and confirm HTTP 200 with no parse errors.

---

## Task 6: Update living documentation and incident knowledge

**Files:**
- Modify: `/Users/myron/IdeaProjects/smhomelab-infrastructure/docs/architecture/observability.md`
- Modify: `/Users/myron/IdeaProjects/smhomelab-infrastructure/docs/architecture/networking-and-access.md`
- Create: `/Users/myron/IdeaProjects/smhomelab-infrastructure/docs/psa/000016-PSA-job-hunter-jvm-heap-alert-gap-000000.md`

**Step 1: Document the observability contract**

Update `observability.md` with:

- JVM heap pressure versus container working-set semantics;
- single-restart and frequent-restart coverage;
- matching-stall and VictoriaTraces ingestion rules;
- the remaining limitations, including natural periods with no trace traffic.

**Step 2: Document the network boundary**

Update `networking-and-access.md` to state that application namespaces may send OTLP/HTTP only to VictoriaTraces TCP 10428, while other monitoring ingress remains denied.

**Step 3: Write the PSA from verified evidence**

Follow current PSA front matter/style. Include the timeline, 256 MiB effective heap despite 1 GiB container, synchronous 7,988-group/21,921-job load, exit-143 alert blind spot, NetworkPolicy trace block, matching selectivity evidence, corrections, alert coverage, rollout evidence, and rollback.

Use production-quality Russian prose consistent with this infrastructure repository. Do not include credentials, raw user preference content, or identifying user UUIDs.

**Step 4: Run docs and repository checks**

Run the documented Markdown/link/front-matter validation and inspect `git diff --check`.

**Step 5: Commit and push infrastructure atomically**

```sh
git add manifests/core/network-policies/monitoring.yaml \
  manifests/monitoring/prometheus-rules/oom-alerts.yaml \
  manifests/monitoring/prometheus-rules/job-hunter-alerts.yaml \
  manifests/monitoring/prometheus-rules/platform-alerts.yaml \
  docs/architecture/observability.md \
  docs/architecture/networking-and-access.md \
  docs/psa/000016-PSA-job-hunter-jvm-heap-alert-gap-000000.md
git commit -m "fix(observability): cover JVM heap and trace ingestion gaps"
git push origin master
```

---

## Task 7: Release API and update the parent gitlink

**Files:**
- Inspect/modify as required by release workflow: `api/.github/workflows/*`
- Modify: root `api` gitlink

**Step 1: Follow the API's existing release mechanism**

Inspect recent tags/releases and workflow inputs. Produce the next patch release using the established non-force path; do not invent a separate image publishing route.

Expected: registry contains the immutable API image and the deployment image updater can select it.

**Step 2: Update the root submodule pointer**

After the API commit is upstream:

```sh
cd /Users/myron/IdeaProjects/job-hunter
git add api
git commit -m "chore: update api for bounded retro filtering"
git push origin master
```

Expected: parent repository references the exact upstream API fix commit.

---

## Task 8: Roll out and verify production behavior

**Files:**
- Update after rollout evidence: `/Users/myron/IdeaProjects/smhomelab-infrastructure/docs/psa/000016-PSA-job-hunter-jvm-heap-alert-gap-000000.md`

**Step 1: Observe Argo CD synchronization**

Wait for the affected deploy, infrastructure, Prometheus rules, NetworkPolicy, and new Job Hunter image to become Synced/Healthy. Use read-only Argo CD and Kubernetes checks; do not force-delete healthy resources.

Expected: no degraded applications and all affected pods Ready.

**Step 2: Verify effective JVM flags everywhere**

For Job Hunter API, email-watcher, and telegram-user-monitor, inspect `/proc/1/cmdline` or `jcmd 1 VM.flags` and confirm effective `MaxRAMPercentage=75.0`. For the 1 GiB Job Hunter container, confirm the maximum heap is approximately 768 MiB rather than 256 MiB.

**Step 3: Verify trace transport**

From the Job Hunter API pod, confirm VictoriaTraces health on TCP 10428. Then observe exporter logs and `vt_rows_ingested_total` through at least one export interval.

Expected: no new connection-refused exporter errors; OTLP row counters advance.

**Step 4: Exercise preference save and bounded cleanup**

Use the existing authenticated application flow without changing preference semantics. Confirm the settings request completes promptly, `cold-filter-retro-*` processes chunks in the background, heap and probes remain healthy, and no restart occurs.

**Step 5: Verify alert resources and states**

Confirm all new rules are loaded by vmalert and evaluate without errors. The trace-ingestion alert should resolve after OTLP counters advance; heap/restart/matching alerts should be inactive under healthy conditions. Do not manufacture a production OOM or restart.

**Step 6: Add rollout evidence to the PSA and push**

Record UTC timestamps, deployed image/version, effective heap, trace counter movement, request outcome, pod restart delta, and final alert states. Commit only if the evidence update changes the PSA:

```sh
git add docs/psa/000016-PSA-job-hunter-jvm-heap-alert-gap-000000.md
git commit -m "docs(psa): record JVM recovery rollout"
git push origin master
```

---

## Task 9: Final verification and cleanup

**Step 1: Audit all working trees**

Run `git status --short --branch` in root, API, deploy worktree, original deploy checkout, and infrastructure. Confirm only the user's pre-existing deploy changes remain outside committed task work.

**Step 2: Run final change audit**

Use the `check-changes` and `verification-before-completion` skills. Compare implementation against the approved design, repository instructions, tests, rendered manifests, live cluster state, documentation, and upstream commits.

**Step 3: Remove only the isolated worktree**

After the branch commit is upstream and verified, remove the specific clean worktree and delete only its local task branch. Do not alter the original dirty deploy checkout.

**Step 4: Report results**

Report root causes, exact commits/releases, verification evidence, any still-firing alerts with reason, and remaining risks. If a required live check cannot be completed, state the concrete blocker rather than claiming completion.
