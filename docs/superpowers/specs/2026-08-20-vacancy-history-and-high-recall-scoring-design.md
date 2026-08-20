# Vacancy History and High-Recall Scoring Design

**Status:** Owner-approved direction, pending written-spec review
**Date:** 2026-08-20

## Context

The current matching pipeline is optimized for avoiding false positives. That no
longer matches the owner's application strategy. Fully remote work remains a hard
requirement, but any plausible Java, Kotlin, or JVM backend position should be
ranked and shown even when the posting is from an agency, written in another
language, asks for more years, mentions an unfamiliar secondary tool, or includes
some full-stack work.

Production evidence shows that score is not separating useful jobs from noise:

- 270 owner-reviewed `APPLIED` groups have an average stored score of 78.8;
- 157 owner-reviewed `IRRELEVANT` groups have an average stored score of 75.1;
- the probability that a random `APPLIED` group scores above a random
  `IRRELEVANT` group is only 0.565;
- recent exact Java/Kotlin backend matches received scores in the 35-58 range
  because of language, staffing-company, seniority, full-stack, or posting-quality
  caps.

These stored decisions span more than one model and prompt era, so they are not a
clean model benchmark. They are still strong evidence that production score is a
poor ranking signal for the owner's real behavior.

The current database also cannot produce a truthful historical matching chart.
Cold rejection and post-AI remote rejection are transient counters and log text.
Only accepted AI scores are stored. A rejected group has no per-user row, and
`jobs.matched_at` cannot distinguish cold rejection from a post-AI remote result.

## Goals

- Add a protected, personalized vacancy-history chart with daily, weekly, and
  monthly time buckets.
- Show all vacancy groups, cold-rejected groups, groups rejected as not fully
  remote after AI inference, AI-scored groups, and median AI score as independently
  toggleable series.
- Support 7-day, 30-day, 90-day, 1-year, custom, and all-time ranges, source filters,
  hover details, and mouse/touch range zoom.
- Preserve strict fully-remote behavior.
- Recalibrate score for high recall among fully remote Java/Kotlin/JVM backend jobs.
- Persist enough per-user matching state for exact statistics after rollout and
  useful, explicitly marked legacy history before rollout.
- Keep counts stable across rematches and vacancy retention.

## Non-goals

- Turning `APPLIED` and `IRRELEVANT` status counts into a dashboard or funnel.
- Relaxing the fully-remote requirement.
- Treating score as a server-side rejection threshold.
- Building a general BI system, arbitrary query builder, or Grafana replacement.
- Persisting model chain-of-thought or rejected-job AI reasoning solely for charts.
- Reconstructing cold versus post-AI rejection exactly for historical data that was
  never stored.

## Product design

### Route and navigation

Add a protected `/statistics` route and a `Statistics` sidebar item next to Jobs.
The chart needs the full content width and must not crowd the Jobs review queue or
its sticky filters. The route uses the existing `read:jobs` permission.

The page is one chart-first surface. It does not render status cards, an apply-rate
funnel, or a large applied-versus-irrelevant summary.

### Chart

The chart uses a time X-axis and two Y-axes:

- left axis: distinct vacancy groups;
- right axis: AI score from 0 to 100.

Default series:

- `All vacancies`: all distinct `job_groups` created in the bucket;
- `Cold rejected`: the user's terminal cold-filter outcome;
- `Not fully remote`: groups that passed cold filtering but whose AI result had
  `inferredRemote=false`;
- `AI scored`: groups accepted by the remote gate and stored with a score;
- `Median score`: median score for `AI scored`, rendered against the right axis.

Each series can be toggled from the legend. The tooltip lists every enabled series
for one bucket. A bottom slider plus wheel, trackpad, and touch gestures controls
the visible range. Presets select 7D, 30D, 90D, 1Y, or ALL. Bucket defaults are
daily through 90 days, weekly through one year, and monthly beyond one year; the
owner can override the bucket.

The source selector accepts zero or more sources. Group counts remain distinct
when a group appears on multiple selected sources. Historical source filtering is
exact only where the decision ledger captured source membership; the API reports
coverage metadata rather than silently presenting incomplete legacy data as exact.

On 390x844, the chart stays horizontally contained, controls wrap above it, the
tooltip remains inside the viewport, and touch data zoom remains usable. The
minimum chart height is 360 px on mobile and 500 px on desktop.

### Legacy boundary

The response includes `exactSince` and per-series coverage. Data before the ledger
migration is rendered with a dashed line and an `Estimated legacy data` label when
classification is incomplete.

`All vacancies` is available from durable `job_groups.created_at`. Existing
`user_job_groups` rows can be backfilled as `AI_SCORED`. Groups with `matched_at`
but no per-user row cannot be split honestly between cold and post-AI remote
rejection; they are backfilled as `LEGACY_REJECTED_UNKNOWN` and shown as an optional
legacy series. They are never guessed into the cold or not-remote lines.

## Data design

### Considered approaches

1. **Current decision ledger, recommended.** Store one current terminal decision
   per `(user_id, group_id)`, anchored to the group's creation date. Rematch
   updates classification and score without double-counting the vacancy. Reads are
   simple, storage is bounded, and the chart answers how vacancies arriving on a
   day are classified now.
2. **Append-only evaluation events.** Preserve every rematch and preference-era
   transition. This supports audit playback but makes ordinary vacancy counts easy
   to double-count and requires run-generation idempotency and event retention that
   the product does not need.
3. **Daily aggregate counters.** Make chart reads cheap, but lose source membership,
   drill-down, correction after rematch, and exact handling of partial failed runs.

The decision ledger provides the smallest durable source of truth that matches the
requested chart semantics.

### `user_job_group_decisions`

Add a Flyway migration after the current `origin/master` schema version. The table
contains:

- non-null UUID primary key;
- `user_id`, with deletion cascading when the user is deleted;
- `group_id`, unique with `user_id` and retained independently of posting cleanup;
- `vacancy_seen_at`, copied from `job_groups.created_at` and never moved by rematch;
- `decided_at`, updated on every successful re-evaluation;
- `outcome`: `COLD_REJECTED`, `AI_REJECTED_REMOTE`, `AI_SCORED`,
  `COLD_ONLY`, or `LEGACY_REJECTED_UNKNOWN`;
- nullable bounded `cold_filter` code;
- nullable `ai_score` and `inferred_remote`;
- the source set and category set captured at decision time;
- standard created and updated timestamps.

The ledger does not store a job description, prompt, model output, or duplicate AI
reasoning. `user_job_groups` remains the source for visible job status and detailed
reasoning.

The matching service upserts one ledger row on every terminal branch. AI failures
are not terminal decisions, remain retryable, and do not create a rejection row.
The terminal decision write completes before the group is marked matched. A retry
of the same group updates the unique ledger row and cannot inflate a daily count.

The retroactive cold-filter worker updates affected ledger outcomes while
preserving `vacancy_seen_at`. Reviewed job statuses remain untouched, matching the
existing contract.

### Retention

Posting retention must not delete decision rows or empty `job_groups`, because they
are the bounded historical index for the chart. The ledger stores only UUIDs,
bounded outcome metadata, source/category sets, and a score, so retaining it does
not retain vacancy descriptions or outreach content.

## API contract

Add `POST /statistics/vacancies/query` under the existing authenticated job-read
scope.

Request:

```json
{
  "from": "2026-07-20T00:00:00Z",
  "to": "2026-08-20T23:59:59Z",
  "bucket": "DAY",
  "sources": ["LINKEDIN", "DOU"]
}
```

`from` and `to` are optional and default to 30 days ending at the injected clock.
The server clamps the range to the available history, validates `from <= to`, and
caps point count by selecting or requiring a coarser bucket. Supported buckets are
`DAY`, `WEEK`, and `MONTH`.

Response:

```json
{
  "from": "2026-07-20T00:00:00Z",
  "to": "2026-08-20T23:59:59Z",
  "bucket": "DAY",
  "exactSince": "2026-08-20T15:00:00Z",
  "sourceCoverageSince": "2026-08-20T15:00:00Z",
  "points": [
    {
      "start": "2026-08-20T00:00:00Z",
      "allVacancies": 1547,
      "coldRejected": 428,
      "notFullyRemote": 1009,
      "aiScored": 110,
      "legacyRejectedUnknown": 0,
      "medianScore": 62.0
    }
  ]
}
```

All vacancy-count series are bucketed by vacancy arrival (`job_groups.created_at`
or the ledger's copied `vacancy_seen_at`), not by scheduler runtime, so a rematch
cannot move a vacancy into a later day.

The service owns aggregation and returns zero-filled buckets. Controllers only map
the authenticated subject and typed request. SQL performs grouped aggregation and
percentile calculation; the UI never derives global statistics from partially
loaded vacancy pages.

## High-recall scoring

### Remote gate

Remote behavior does not change:

- explicit `remote=false` is cold-rejected when `remoteOnly=true`;
- unknown remote status is inferred by AI;
- only explicit fully remote wording yields `inferredRemote=true`;
- hybrid, partial remote, required office attendance, and no remote signal yield
  `false`;
- `inferredRemote=false` is rejected after AI regardless of score.

### Ranking policy

Replace the skeptical recruiter policy with a high-recall JVM-backend ranking
policy. Score ranks already-eligible remote opportunities; it does not decide
whether the owner is allowed to apply.

Hard low scores remain appropriate when the primary work is not Java, Kotlin, or
closely related JVM backend engineering, or when the role is primarily QA/SDET,
DevOps/SRE, frontend, mobile, data/ML, product, sales, or people management.

The following must not cap an otherwise plausible Java/Kotlin backend role:

- another language in the posting or an unproven language requirement;
- staffing agency, consultancy, aggregator, or thin description;
- a request for more or fewer years of experience;
- middle, senior, staff, lead, or architect wording when backend implementation is
  still a material responsibility;
- missing secondary frameworks, cloud products, databases, or domain experience;
- full-stack wording when Java/Kotlin backend work is material.

Calibration:

- 85-100: direct Java/Kotlin/JVM backend match;
- 70-84: strong backend match with meaningful but acceptable gaps;
- 55-69: plausible adjacent JVM, backend-heavy full-stack, or legacy Java role;
- 0-54: primary role or primary implementation stack is materially different.

The model still returns structured `reasoning`, `score`, and `inferredRemote`.
Reasoning names transferable gaps without converting them into artificial caps.

### Evaluation

The existing owner-labeled local evaluation set remains private and gitignored.
Before rollout, run the new prompt against the configured production model and the
fallback model. Report recall and false negatives at score thresholds 55, 60, and
70, AUC, applied/irrelevant medians, and the worst disagreements.

Acceptance prioritizes recall:

- no exact fully remote Java/Kotlin backend example receives a hard-disqualifier
  score solely for language, company type, years, secondary tools, or posting
  quality;
- owner-labeled `APPLIED` recall at threshold 60 improves over the stored 94.8%
  baseline and reaches at least 98% on the fixed local fixture;
- every remaining false negative is reviewed manually before rollout;
- remote inference cases are reviewed separately and are not weakened to improve
  score metrics.

The paid-provider benchmark is an explicit operational evaluation, not part of the
normal unit-test task.

## UI implementation direction

Use Apache ECharts directly through its tree-shakable core API. Add only the line
chart, grid, legend, tooltip, data zoom, dataset, and canvas renderer modules used
by this page. Do not add a React wrapper dependency.

A focused `VacancyHistoryChart` component owns initialization, `setOption`, theme
updates, `ResizeObserver` resizing, and `dispose()` cleanup. A TanStack Query hook
owns server data. Date range, bucket, and source filters live in URL search params
so the graph is shareable and browser navigation works.

The UI displays loading, empty, partial-legacy, and API-error states. It never
labels legacy unknown rejection as cold or AI remote rejection.

## Failure behavior

- A matching AI failure remains absent from terminal decision counts and is retried
  under the existing matching policy.
- A decision-ledger write failure prevents the corresponding jobs from being marked
  matched, so the run retries rather than losing analytics state.
- Statistics query timeout or failure affects only the Statistics page and uses the
  existing centralized API error handling.
- Empty ranges render an empty chart with a clear message, not zero-valued fake
  history.
- A source filter extending before source coverage shows a visible coverage warning.

## Verification

### API

- Unit-test all matching terminal branches writing the correct ledger outcome.
- Prove AI failure creates no terminal decision and leaves the group retryable.
- Prove rematch updates one row without moving `vacancy_seen_at` or inflating daily
  counts.
- Integration-test migration, legacy backfill, source/category storage, zero-filled
  buckets, median score, authorization, range validation, and retention behavior.
- Keep matching documentation and the operations runbook aligned with the durable
  ledger.

### UI

- Test request shape and query-key behavior with MSW.
- Test loading, empty, legacy-warning, source-coverage-warning, and successful
  states with React Testing Library.
- Test ECharts lifecycle through a narrow adapter: initialize once, resize on
  container change, update options, and dispose on unmount.
- Run lint, format check, unit tests, and production build.
- Browser-check desktop and 390x844 layouts in dark and light themes.

### End to end

- In a local integrated environment, ingest known jobs covering every terminal
  outcome and verify the resulting chart points.
- Rematch the fixture and prove unique vacancy counts remain stable while outcome
  and score update.
- After deployment, compare one day's ledger aggregates with matching completion
  logs before relying on the graph operationally.

## Rollout

1. Fast-forward API and UI submodules to their current upstream masters and resolve
   the next Flyway migration number before editing.
2. Add the decision ledger, legacy backfill, pipeline writes, aggregation query, and
   authenticated API endpoint.
3. Recalibrate the prompt and run the owner-labeled benchmark without changing the
   remote gate.
4. Add the protected Statistics route, ECharts dependency, query hook, chart, and
   responsive states.
5. Verify both repositories and update living documentation.
6. Deploy API before UI, confirm exact tracking begins, then deploy UI.
7. Rematch only after the owner reviews the benchmark report; deployment itself does
   not automatically rewrite all historical scores.
