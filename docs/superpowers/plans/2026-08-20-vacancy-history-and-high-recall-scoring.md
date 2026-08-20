# Vacancy History and High-Recall Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for implementation. Backend and UI repository tasks may run in parallel after the contract and upstream bases are fixed; each repository receives spec-compliance and code-quality review before integration. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a personalized stock-style vacancy history chart and recalibrate AI ranking for high recall on fully remote Java/Kotlin/JVM backend jobs.

**Architecture:** The API persists one current terminal matching decision per user and vacancy group, aggregates arrival-date buckets through a protected statistics endpoint, and keeps the existing strict remote gate. The UI adds a protected full-width Statistics route rendered with tree-shaken Apache ECharts modules. Legacy decisions are backfilled without inventing cold-versus-remote classifications.

**Tech Stack:** Kotlin 2.1, Spring Boot 3.5, JPA, PostgreSQL 16, Flyway, JUnit 5, Testcontainers, React 19, TypeScript 5.9, Ant Design 6, TanStack Query 5, Apache ECharts, Vitest, React Testing Library, MSW.

---

### Task 1: Synchronize the implementation bases

**Files:**
- Update gitlink working trees: `api/`, `ui/`
- Verify: `api/src/main/resources/db/migration/`
- Verify: `ui/src/app/routes.tsx`

- [ ] **Step 1: Confirm both submodule worktrees are clean**

Run:

```bash
git -C api status --short
git -C ui status --short
```

Expected: no output from either command.

- [ ] **Step 2: Fast-forward local masters without touching other worktrees**

Run:

```bash
git -C api merge --ff-only origin/master
git -C ui merge --ff-only origin/master
```

Expected: API reaches `f80f1b1` or newer and UI reaches `744556d` or newer with no merge commit.

- [ ] **Step 3: Establish fresh baselines**

Run:

```bash
cd api && ./gradlew test --tests '*JobMatchingServiceTest' && cd ..
cd ui && npm test -- --run src/features/jobs && cd ..
```

Expected: both focused baseline suites exit 0.

### Task 2: Persist a bounded per-user matching decision ledger

**Files:**
- Create: `api/src/main/resources/db/migration/V28__add_user_job_group_decisions.sql`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/statistics/MatchingDecisionOutcome.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/statistics/UserJobGroupDecisionEntity.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/statistics/UserJobGroupDecisionRepository.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/statistics/UserJobGroupDecisionFacade.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/statistics/MatchingDecisionService.kt`
- Test: `api/src/test/kotlin/com/mshykhov/jobhunter/application/statistics/UserJobGroupDecisionFacadeIntegrationTest.kt`
- Test: `api/src/test/kotlin/com/mshykhov/jobhunter/application/statistics/MatchingDecisionServiceTest.kt`

- [ ] **Step 1: Write failing migration and persistence tests**

Cover these observable contracts:

```kotlin
@Test
fun `upsert preserves vacancy seen time while replacing outcome and score`() {
    val original = service.record(scoredDecision(score = 38, vacancySeenAt = firstSeen))
    val rematched = service.record(scoredDecision(score = 82, vacancySeenAt = laterSeen))

    assertThat(rematched.id).isEqualTo(original.id)
    assertThat(rematched.vacancySeenAt).isEqualTo(firstSeen)
    assertThat(rematched.aiScore).isEqualTo(82)
}

@Test
fun `legacy backfill does not invent rejection type`() {
    assertThat(backfilled.outcome).isEqualTo(MatchingDecisionOutcome.LEGACY_REJECTED_UNKNOWN)
}
```

The integration test must also prove unique `(user_id, group_id)`, source/category array persistence, user-deletion cascade, and that deleting jobs does not delete the decision row.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
cd api
./gradlew test --tests '*MatchingDecisionServiceTest' --tests '*UserJobGroupDecisionFacadeIntegrationTest'
```

Expected: FAIL because the statistics decision types and migration do not exist.

- [ ] **Step 3: Add the Flyway schema and honest legacy backfill**

Create a table equivalent to:

```sql
CREATE TABLE user_job_group_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id UUID NOT NULL REFERENCES job_groups(id),
    vacancy_seen_at TIMESTAMPTZ NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL,
    outcome VARCHAR(40) NOT NULL,
    cold_filter VARCHAR(60),
    ai_score INTEGER,
    inferred_remote BOOLEAN,
    sources TEXT[] NOT NULL DEFAULT '{}',
    categories TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_job_group_decision UNIQUE (user_id, group_id),
    CONSTRAINT ck_user_job_group_decision_outcome CHECK (
        outcome IN ('COLD_REJECTED', 'AI_REJECTED_REMOTE', 'AI_SCORED', 'COLD_ONLY', 'LEGACY_REJECTED_UNKNOWN')
    ),
    CONSTRAINT ck_user_job_group_decision_score CHECK (ai_score IS NULL OR ai_score BETWEEN 0 AND 100)
);
```

Backfill visible `user_job_groups` as `AI_SCORED`. Backfill evaluated groups without a user row for each existing preference as `LEGACY_REJECTED_UNKNOWN`. Use `job_groups.created_at` for `vacancy_seen_at`; never infer cold or remote outcome from current `jobs.remote`.

- [ ] **Step 4: Implement idempotent decision upsert**

Expose one value request with all terminal metadata:

```kotlin
data class MatchingDecision(
    val user: UserEntity,
    val group: JobGroupEntity,
    val vacancySeenAt: Instant,
    val outcome: MatchingDecisionOutcome,
    val coldFilter: String? = null,
    val aiScore: Int? = null,
    val inferredRemote: Boolean? = null,
    val sources: Set<JobSource>,
    val categories: Set<Category>,
)
```

The transactional service loads by user and group, preserves the stored `vacancySeenAt`, replaces terminal fields, and uses the injected `Clock` for `decidedAt`.

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run:

```bash
./gradlew test --tests '*MatchingDecisionServiceTest' --tests '*UserJobGroupDecisionFacadeIntegrationTest'
```

Expected: PASS.

- [ ] **Step 6: Commit the ledger**

```bash
git add src/main src/test
git commit -m "feat(statistics): persist matching decisions"
```

### Task 3: Record every terminal matching outcome without weakening remote-only

**Files:**
- Modify: `api/src/main/kotlin/com/mshykhov/jobhunter/application/matching/JobMatchingService.kt`
- Modify: `api/src/main/kotlin/com/mshykhov/jobhunter/application/matching/ColdFilterRetroService.kt`
- Modify: `api/src/test/kotlin/com/mshykhov/jobhunter/application/matching/JobMatchingServiceTest.kt`
- Modify: `api/src/test/kotlin/com/mshykhov/jobhunter/application/matching/ColdFilterRetroServiceTest.kt`

- [ ] **Step 1: Add failing terminal-branch tests**

Assert exact calls for:

```kotlin
verify { decisionService.record(match { it.outcome == COLD_REJECTED && it.coldFilter == "excludedTitleKeyword" }) }
verify { decisionService.record(match { it.outcome == AI_REJECTED_REMOTE && it.inferredRemote == false }) }
verify { decisionService.record(match { it.outcome == AI_SCORED && it.aiScore == 72 }) }
verify { decisionService.record(match { it.outcome == COLD_ONLY }) }
verify(exactly = 0) { decisionService.record(any()) } // AI failure remains retryable
```

Also prove `remoteOnly=true` still rejects explicit on-site jobs before AI and rejects inferred non-remote jobs after AI.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
./gradlew test --tests '*JobMatchingServiceTest' --tests '*ColdFilterRetroServiceTest'
```

Expected: FAIL because the pipeline does not record decisions.

- [ ] **Step 3: Record terminal decisions in the existing branch order**

Pass the full group job list to decision construction so sources are captured from
all group members. Let a decision-write exception fail the group before
`matched_at` is updated. Do not catch and discard ledger errors.

The retro worker changes the outcome to `COLD_REJECTED` when current preferences
reject a NEW group, preserving reviewed statuses and the ledger's arrival time.

- [ ] **Step 4: Run and verify GREEN**

Run:

```bash
./gradlew test --tests '*JobMatchingServiceTest' --tests '*ColdFilterRetroServiceTest'
```

Expected: PASS.

- [ ] **Step 5: Commit pipeline recording**

```bash
git add src/main src/test
git commit -m "feat(matching): record terminal decisions"
```

### Task 4: Add the personalized vacancy-history query API

**Files:**
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/statistics/StatisticsBucket.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/application/statistics/VacancyStatisticsService.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/statistics/StatisticsController.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/statistics/dto/VacancyStatisticsQueryRequest.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/statistics/dto/VacancyStatisticsPointResponse.kt`
- Create: `api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/statistics/dto/VacancyStatisticsResponse.kt`
- Modify: `api/src/main/kotlin/com/mshykhov/jobhunter/infrastructure/security/SecurityConfig.kt`
- Test: `api/src/test/kotlin/com/mshykhov/jobhunter/application/statistics/VacancyStatisticsServiceTest.kt`
- Test: `api/src/test/kotlin/com/mshykhov/jobhunter/api/rest/statistics/StatisticsControllerIntegrationTest.kt`

- [ ] **Step 1: Write failing aggregation and endpoint tests**

Create fixture decisions across empty and non-empty days. Assert:

```kotlin
assertThat(response.points).containsExactly(
    point("2026-08-19T00:00:00Z", all = 3, cold = 1, remote = 1, scored = 1, median = 72.0),
    point("2026-08-20T00:00:00Z", all = 0, cold = 0, remote = 0, scored = 0, median = null),
)
```

Controller coverage must assert bearer subject isolation, `read:jobs` scope,
request validation, source filtering without double-counting multi-source groups,
legacy coverage metadata, and no `/api` prefix.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
./gradlew test --tests '*VacancyStatisticsServiceTest' --tests '*StatisticsControllerIntegrationTest'
```

Expected: FAIL because `/statistics/vacancies/query` is absent.

- [ ] **Step 3: Implement bounded aggregation**

Implement `POST /statistics/vacancies/query` with request defaults of the previous
30 days and `DAY`. Validate `from <= to`; support `DAY`, `WEEK`, and `MONTH`; reject
ranges that would exceed 400 returned points at the chosen bucket.

Use distinct group aggregation and PostgreSQL `percentile_cont(0.5)` for score.
Return zero-filled buckets in chronological order and the migration timestamp as
`exactSince` and `sourceCoverageSince`.

- [ ] **Step 4: Run and verify GREEN**

Run:

```bash
./gradlew test --tests '*VacancyStatisticsServiceTest' --tests '*StatisticsControllerIntegrationTest'
```

Expected: PASS.

- [ ] **Step 5: Commit the API**

```bash
git add src/main src/test
git commit -m "feat(statistics): expose vacancy history"
```

### Task 5: Recalibrate scoring for high recall while preserving remote inference

**Files:**
- Modify: `api/src/main/kotlin/com/mshykhov/jobhunter/application/ai/JobRelevanceEvaluator.kt`
- Modify: `api/src/test/kotlin/com/mshykhov/jobhunter/application/ai/JobRelevanceEvaluatorTest.kt`
- Modify: `api/eval/prompts/` only if the local ignored evaluation workspace is present; do not commit private fixtures
- Modify: `api/docs/job-matching-architecture.md`

- [ ] **Step 1: Write a failing prompt-contract test**

Capture the system prompt passed to the chat client and assert it contains the new
ranking contract and excludes the obsolete caps:

```kotlin
assertThat(systemPrompt).contains("maximize recall for fully remote Java, Kotlin, and JVM backend roles")
assertThat(systemPrompt).contains("85-100: direct Java/Kotlin/JVM backend match")
assertThat(systemPrompt).doesNotContain("staffing-agency or aggregator reposts")
assertThat(systemPrompt).doesNotContain("Language requirement (caps the score at 40)")
assertThat(systemPrompt).doesNotContain("Seniority gap of 2+ levels")
```

Keep existing structured-output and strict remote-inference assertions.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
./gradlew test --tests '*JobRelevanceEvaluatorTest'
```

Expected: FAIL on the new prompt assertions.

- [ ] **Step 3: Replace only the ranking policy**

Use this calibration:

```text
85-100 direct Java/Kotlin/JVM backend match
70-84 strong backend match with acceptable gaps
55-69 adjacent JVM, backend-heavy full-stack, or legacy Java
0-54 materially different primary role or stack
```

Explicitly forbid caps for posting language, agency/consultancy, years, level,
secondary tools, domain, thin description, or backend-heavy full-stack wording.
Do not change `inferredRemote`: only fully remote wording returns true; hybrid,
partial office, or no signal returns false.

- [ ] **Step 4: Run tests and the owner-labeled evaluation**

Run:

```bash
./gradlew test --tests '*JobRelevanceEvaluatorTest'
```

Expected: PASS.

If the private local fixture and configured production-model endpoint are
available, run the benchmark and save its report outside Git. Required report:
recall and false negatives at 55/60/70, AUC, applied and irrelevant medians, and
every remaining false negative. Do not spend a paid fallback key silently.

- [ ] **Step 5: Commit scoring and documentation**

```bash
git add src/main src/test docs/job-matching-architecture.md
git commit -m "fix(matching): rank JVM backend for high recall"
```

### Task 6: Add the typed statistics client and ECharts lifecycle adapter

**Files:**
- Modify: `ui/package.json`
- Modify: `ui/package-lock.json`
- Modify: `ui/src/lib/api.ts` or the existing API path catalogue location
- Create: `ui/src/features/statistics/types.ts`
- Create: `ui/src/features/statistics/constants.ts`
- Create: `ui/src/features/statistics/hooks/useVacancyStatistics.ts`
- Create: `ui/src/features/statistics/components/EChartsView.tsx`
- Test: `ui/src/features/statistics/hooks/__tests__/useVacancyStatistics.test.tsx`
- Test: `ui/src/features/statistics/components/__tests__/EChartsView.test.tsx`
- Modify: `ui/src/mocks/fixtures.ts`
- Modify: `ui/src/mocks/handlers.ts`

- [ ] **Step 1: Install the approved chart dependency**

Run:

```bash
cd ui
npm install echarts
```

Expected: `echarts` is the only new runtime dependency; no React wrapper is added.

- [ ] **Step 2: Write failing API-contract and lifecycle tests**

Assert the hook sends:

```json
{"from":"2026-07-20T00:00:00.000Z","to":"2026-08-20T23:59:59.999Z","bucket":"DAY","sources":["LINKEDIN"]}
```

Assert the adapter initializes once, updates through `setOption`, calls `resize`
from `ResizeObserver`, and calls `dispose` on unmount.

- [ ] **Step 3: Run and verify RED**

Run:

```bash
npm test -- --run src/features/statistics
```

Expected: FAIL because the statistics feature does not exist.

- [ ] **Step 4: Implement typed server state and the tree-shaken adapter**

Import only ECharts core, `LineChart`, `GridComponent`, `LegendComponent`,
`TooltipComponent`, `DataZoomComponent`, `DatasetComponent`, and
`CanvasRenderer`. The hook uses a hierarchical query key:

```ts
["statistics", "vacancies", query]
```

URL state remains outside the server-data hook.

- [ ] **Step 5: Run and verify GREEN**

Run:

```bash
npm test -- --run src/features/statistics
```

Expected: PASS.

- [ ] **Step 6: Commit the client foundation**

```bash
git add package.json package-lock.json src
git commit -m "feat(statistics): add vacancy chart client"
```

### Task 7: Build the protected stock-style Statistics page

**Files:**
- Create: `ui/src/features/statistics/hooks/useStatisticsFilters.ts`
- Create: `ui/src/features/statistics/components/StatisticsToolbar.tsx`
- Create: `ui/src/features/statistics/components/VacancyHistoryChart.tsx`
- Create: `ui/src/features/statistics/components/StatisticsPage.tsx`
- Create: `ui/src/features/statistics/utils/chartOptions.ts`
- Modify: `ui/src/app/routes.tsx`
- Modify: `ui/src/components/Layout/Sidebar.tsx`
- Modify: `ui/src/styles/global.css`
- Test: `ui/src/features/statistics/components/__tests__/StatisticsPage.test.tsx`
- Test: `ui/src/features/statistics/utils/__tests__/chartOptions.test.ts`

- [ ] **Step 1: Write failing page behavior tests**

Cover loading, empty, API error, exact data, dashed legacy series, source coverage
warning, URL range/bucket/source state, and chart series mapping. Verify the page
does not render Applied, Irrelevant, or an application funnel.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
npm test -- --run src/features/statistics
```

Expected: FAIL because the route and page are absent.

- [ ] **Step 3: Implement the chart-first route**

Add protected `/statistics` under the same `ProtectedRoute` and `read:jobs`
navigation visibility as Jobs. Render one full-width chart with:

- toggleable all/cold/not-remote/scored/median series;
- left count and right 0-100 score axes;
- axis tooltip;
- slider and inside data zoom;
- 7D/30D/90D/1Y/ALL presets;
- DAY/WEEK/MONTH override;
- multi-source selector;
- legacy and source-coverage warnings.

Use Ant Design tokens and `statistics-` prefixed global classes. At 390x844,
controls wrap and chart height remains at least 360 px.

- [ ] **Step 4: Run and verify GREEN**

Run:

```bash
npm test -- --run src/features/statistics
```

Expected: PASS.

- [ ] **Step 5: Commit the page**

```bash
git add src
git commit -m "feat(statistics): add vacancy history page"
```

### Task 8: Synchronize documentation and verify the integrated feature

**Files:**
- Modify: `api/docs/job-matching-architecture.md`
- Modify: `api/docs/runbook.md`
- Modify: `api/README.md`
- Modify: `ui/README.md`
- Modify: root `README.md` only if its component contract needs the new route noted
- Update gitlinks: root `api`, `ui`

- [ ] **Step 1: Document semantics and operational checks**

Document exact-versus-legacy coverage, arrival-date bucketing, rematch stability,
remote gate semantics, high-recall score calibration, and a SQL/log comparison for
the first production day.

- [ ] **Step 2: Run complete API verification**

Run:

```bash
cd api
./gradlew ktlintFormat
./gradlew build
npm run rulesync:verify
```

Expected: every command exits 0.

- [ ] **Step 3: Run complete UI verification**

Run:

```bash
cd ui
npm run format
npm run lint
npm run format:check
npm run test
npm run build
npm run rulesync:verify
```

Expected: every command exits 0.

- [ ] **Step 4: Browser verification**

Run the mock UI and verify `/statistics` in dark and light themes at desktop and
390x844. Confirm legend toggles, tooltip, source selection, presets, slider, wheel,
and touch zoom. Close the named browser session afterward.

- [ ] **Step 5: Review repository diffs and commits**

Run:

```bash
git -C api status --short
git -C ui status --short
git diff --submodule=log -- api ui
git status --short
```

Expected: API and UI are clean; root shows only intentional gitlink changes plus
pre-existing unrelated `docs/ideas/`.

- [ ] **Step 6: Commit root integration**

```bash
git add api ui README.md docs/superpowers/plans/2026-08-20-vacancy-history-and-high-recall-scoring.md
git commit -m "feat: integrate vacancy history analytics"
```

Do not add the unrelated `docs/ideas/` file.
