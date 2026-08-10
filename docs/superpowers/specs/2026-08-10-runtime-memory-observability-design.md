# Runtime Memory and Observability Recovery

## Incident evidence

On 2026-08-10, saving Job Hunter matching preferences synchronously triggered
`ColdFilterRetroService`. The service fetched 7,988 `NEW` user job groups and
21,921 associated jobs through an entity graph. Those rows contained about 61 MiB
of descriptions and 185 MiB of raw JSON before JVM object overhead.

The deployment declared `JAVA_OPTS=-XX:MaxRAMPercentage=75.0`, but the image starts
the application with exec-form `java -jar app.jar`. Java does not consume
`JAVA_OPTS` itself. The live process therefore used the default 25 percent heap,
with `MaxHeapSize=256 MiB` inside a 1 GiB container. The retro filter exhausted the
Java heap, blocked health probes, and was terminated by the liveness probe with
exit code 143.

The existing alerts did not match this failure mode:

- Kubernetes reported `Error`, not `OOMKilled`, because liveness sent SIGTERM.
- Container working set peaked at 56.8 percent, below the 90 percent alert.
- Only one restart occurred in an hour, below the five-restart threshold.
- The external outage was shorter than the five-minute synthetic threshold.

Separately, the monitoring namespace NetworkPolicy rejects OTLP traffic from
application namespaces. The API produced 6,600 trace-export connection errors in
24 hours even though VictoriaTraces itself was healthy.

## Scope

The recovery covers all JVM workloads managed by `smhomelab-deploy`, the shared
monitoring boundary in `smhomelab-infrastructure`, and the Job Hunter retro-filter
implementation. It also adds documentation and alerts that apply beyond Job
Hunter.

The matching score calibration is not changed. During the inspected window the
matcher completed without AI failures: 212 AI evaluations produced 26 saved
results, while 186 were rejected because `remoteOnly=true` and the model inferred
that the jobs were not fully remote. Of 23 newly created groups, two scored at
least 70. That is selective behavior, not the runtime failure.

## Design

### JVM configuration

Replace `JAVA_OPTS` with `JAVA_TOOL_OPTIONS` for every JVM workload in the deploy
repository. The latter is consumed by the JVM for both direct `java` entrypoints
and generated application launch scripts. Preserve the existing 75 percent
maximum-RAM policy and verify effective flags in every live process after rollout.

### Memory-bounded retro filtering

Preference persistence remains the source of a `PreferenceChangedEvent`, but the
post-commit retro filter moves to a dedicated bounded single-worker executor. This
keeps the HTTP response independent from historical cleanup while preventing
concurrent full-history scans.

The listener first loads only matching user-group identifiers. It processes those
identifiers in fixed-size chunks, fetching the existing group-and-jobs entity graph
only for the active chunk. Rejected groups are deleted in a batch, changes are
flushed, and the persistence context is cleared before the next chunk. A failure is
logged with the user identifier and does not roll back the already-committed
preference update.

No schema or new dependency is required. Existing cold-filter semantics and the
longest-description representative selection remain unchanged.

### Network boundary

Keep the monitoring namespace protected by default. Add a narrow additive
NetworkPolicy that selects only VictoriaTraces pods and permits TCP 10428 from
namespaces labeled `tier=application`. Other monitoring services remain
inaccessible from application namespaces.

### Alerts

Extend shared monitoring with:

- JVM heap pressure based on `jvm_memory_used_bytes / jvm_memory_max_bytes`, so a
  runtime heap ceiling is visible even when the container has free memory;
- a production-container restart warning at one restart, excluding expected dev
  churn and retaining the existing frequent-restart alert;
- Job Hunter matching-stalled detection when backlog is positive but evaluation
  counters do not advance;
- VictoriaTraces ingestion failure when its scrape target is healthy but
  `vt_rows_ingested_total{type="opentelemetry_traces_otlphttp_protobuf"}` does not
  advance for 30 minutes.

Alert expressions must be evaluated against current VictoriaMetrics series before
deployment. Critical routing remains unchanged.

## Verification and rollout

1. Add regression tests that prove retro filtering processes bounded chunks and
   schedules work outside the preference request transaction.
2. Run focused matching tests, the full API test suite, formatting, static checks,
   and image build.
3. Render and validate deploy and infrastructure Helm/Kubernetes output, including
   policy and Prometheus rule syntax.
4. Commit and push each repository atomically. Update the parent submodule pointer
   only after the API commit is upstream.
5. Sync through Argo CD and verify live JVM flags for every managed JVM workload.
6. From Job Hunter API, verify VictoriaTraces `/health` and successful OTLP export.
7. Save matching preferences and confirm an immediate successful response, bounded
   background cleanup, stable heap, healthy probes, and no new exporter errors.
8. Observe matching, restart, heap, and trace metrics through at least one complete
   matching cycle.

## Rollback

Each repository uses a separate Conventional Commit. Reverting the deploy commit
restores the prior JVM environment; reverting the API commit restores synchronous
cleanup; reverting the infrastructure commit removes the policy and alerts. No
database rollback is required.
