# Automation Runner Health and Canary

**Status:** Approved design; implementation pending.

## Context

Job Hunter will add a Codex-driven workflow for submitting job applications. The
first implementation slice must prove that the execution environment is healthy
before any vacancy queue, form filling, or submission capability is introduced.
It must also alert the owner when that environment stops working.

The automation surface is private and single-owner. Existing public vacancy
pages remain public and are outside this design.

## Goals

- Introduce a Job Hunter-specific automation runtime without creating a second
  business backend or source of truth.
- Verify the launcher, Job Hunter API, PostgreSQL, Chrome profile, Playwright,
  MCP transports, and Codex authentication through layered probes.
- Publish bounded operational metrics and actionable alerts.
- Show the current runner state only to the configured Job Hunter owner.
- Establish the minimal owner delegation used to enable or disable private
  automation health monitoring and bind the runner identity.
- Fail closed: an unhealthy or uncertain runner must never claim application
  work when application processing is added later.

## Non-goals

- Reading or claiming the vacancy queue.
- Filling forms, uploading documents, or submitting applications.
- Adding source- or ATS-specific browser adapters.
- Building schedules, leases, submit fencing, or application audit records.
- Supporting multiple automation owners.
- Creating a separate workflow service, database, broker, or observability stack.
- Changing the existing public vacancy catalogue.

## Repository boundaries

### `job-hunter-automation`

Create a Job Hunter-specific repository and add it to this coordinating
repository as the `automation/` submodule. Its intended layout is:

```text
automation/
  launcher/          # systemd-supervised heartbeat and codex exec launcher
  browser-runner/    # typed local MCP backed by Playwright
  probes/            # deterministic browser, MCP, and Codex canaries
  skills/            # versioned job-application skill, added in a later slice
  adapters/          # source and ATS adapters, added in later slices
  packaging/         # systemd units and runtime configuration
```

TypeScript on Node.js is the preferred runtime because Playwright and MCP are
first-class dependencies there. The repository owns execution only. It has no
business database and does not persist application workflow state. The protected
persistent Chrome profile is runtime data outside the Git repository. One
systemd-supervised launcher serializes deterministic probes and Codex canaries;
each local stdio Browser Runner opens and closes the profile within that critical
section, so two processes never own it concurrently.

### `job-hunter-api`

The Kotlin API remains the durable capability and policy boundary. This slice
adds the minimal owner delegation, current runner-health snapshot, authenticated
machine endpoints, an owner-only REST projection, and Micrometer metrics. The
delegation in this slice grants health reporting only; later versions add
explicit application capabilities. Later slices also add schedules, work claims,
leases, submit fencing, audit/outbox, and the application MCP use cases to the
same backend.

### `job-hunter-ui`

The React UI adds an owner-only read-only Automation status surface. It displays
overall and component state, last successful checks, and a sanitized failure
reason. It does not expose credentials, browser data, raw probe output, or an
interactive control plane in this slice.

### `smhomelab-infrastructure`

The infrastructure repository owns LXD provisioning, secret wiring, monitoring
rules, Alertmanager routing, and the Grafana dashboard. New rules extend the
existing `job-hunter-alerts.yaml`; they do not introduce another notification
service.

### Existing repositories

The n8n repository is unchanged. The root Job Hunter repository coordinates the
new submodule and cross-repository documentation.

## Security and ownership

V1 has exactly one automation owner. The owner is identified by the immutable
OIDC issuer and subject pair, never by email or a caller-provided user ID.

- Interactive Automation REST endpoints require the normal user session,
  dedicated automation scopes, and an exact owner match.
- The runner uses a short-lived M2M identity bound server-side to the owner's
  automation delegation. Machine payloads cannot select or switch users.
- Runner machine endpoints use TLS and accept only the dedicated short-lived M2M
  issuer plus health-reporting scope. Browser Runner MCP uses local stdio and
  opens no network listener.
- The persistent Chrome profile is dedicated to automation and may hold the
  owner's authenticated site sessions. Its files, cookies, and credentials never
  enter API payloads, telemetry, probe output, or Git.
- An expired site session or authentication challenge produces `AUTH_REQUIRED`.
  The runner stops before work and waits for manual re-authentication.
- Public ATS pages may be probed without a site login in later slices, but every
  action still requires the active owner delegation.

The user does not need to remain logged into the Job Hunter UI or keep a laptop
online. The scheduled runner authenticates independently after the owner enables
automation once.

## Health model

The API stores one current snapshot per configured runner. Heartbeats replace the
current snapshot rather than appending one database record per minute. Component
snapshots and typed probe snapshots are stored in separate JSONB maps. Each probe
snapshot contains only an allowlisted outcome and reason, duration in
milliseconds, consecutive-failure count, and last-success timestamp. The runner
snapshot otherwise contains only stable identifiers, component states, check
timestamps, the runner generation, and probe versions. It contains no exception
text, prompt, URL, cookie, credential, DOM content, or personal value.
An immutable bounded runner-health transition is recorded only when a component
changes state or recovers, not for every heartbeat. This is operational history,
not application audit or event sourcing.

The component set is bounded:

- launcher;
- Job Hunter API and PostgreSQL reachability;
- Chrome process and profile access;
- Playwright browser control;
- Browser Runner MCP;
- Job Hunter MCP transport;
- Codex authentication and required MCP initialization.

Each component and the derived overall state use:

- `READY`: the most recent required probe succeeded within its freshness window;
- `DEGRADED`: the component responds but a required capability is failing;
- `AUTH_REQUIRED`: browser-site or Codex authentication requires owner action;
- `UNAVAILABLE`: the component cannot be reached or has no fresh evidence.

The overall state is `READY` only when every capability required for unattended
execution is `READY`. Authentication failure takes precedence as
`AUTH_REQUIRED`; another non-ready required component produces `DEGRADED` or
`UNAVAILABLE`. Future queue claims must require a fresh `READY` snapshot in the
same backend authorization path that issues the claim.

## Layered probes

### Heartbeat

The launcher sends an authenticated heartbeat every minute. It includes runner
identity, monotonic generation, launcher version, typed snapshots for the bounded
`HEARTBEAT`, `PREFLIGHT`, and `CODEX` probes, and timestamps. Outcomes are bounded
to `SUCCESS` and `FAILURE`; reasons use the shared reason vocabulary. The backend
rejects stale generations and timestamps outside a small clock-skew window. A
successful HTTP request alone is not treated as browser readiness.

### Deterministic preflight

Every five minutes, without invoking a model, the runner verifies:

1. the authenticated Job Hunter machine endpoint and its database-backed write;
2. Chrome process availability and protected profile readability;
3. Playwright control by opening and observing a safe local fixture page;
4. Browser Runner MCP `initialize` and `tools/list`;
5. Job Hunter MCP `initialize` and `tools/list`.

The first slice may expose no application tools yet. The MCP probe validates the
transport and protocol response without adding a temporary model-visible health
tool. Once application tools exist, the probe also checks their versioned names
and schema hashes.

### Codex canary

By default every six hours, the launcher runs one minimal
`codex exec --json --ephemeral` canary under the dedicated automation profile. It
proves that subscription authentication can refresh, the process starts, required
MCP connections initialize, and the process terminates successfully. The canary
cannot claim work, read vacancies, navigate external sites, or call submission
capabilities.

The launcher consumes the JSONL stream in memory, derives a bounded result and
token count, reports that summary, and discards raw prompts, model text, and tool
payloads. Failures use bounded backoff and never create a tight authentication or
model retry loop. The cadence is configurable, but disabling the canary makes its
component non-ready after the configured freshness window.

## Data flow

```text
systemd
  -> launcher
      -> heartbeat and deterministic probes
      -> periodic minimal codex exec
      -> authenticated machine status endpoint
          -> Job Hunter API/PostgreSQL current snapshot
              -> owner-only REST status
              -> Micrometer/Prometheus metrics
                  -> VictoriaMetrics
                      -> Alertmanager -> private Telegram/Pushover routes
                      -> Grafana
```

No probe accesses application work. No observability component becomes a source
of application truth.

## Metrics

The API is the only application-metric producer. Initial metric families are:

- `jobhunter_automation_enabled`;
- `jobhunter_automation_runner_last_heartbeat_timestamp_seconds`;
- `jobhunter_automation_component_state{component,state}`;
- `jobhunter_automation_probe_total{probe,outcome,reason}`;
- `jobhunter_automation_probe_duration_seconds{probe}`;
- `jobhunter_automation_probe_consecutive_failures{probe}`;
- `jobhunter_automation_probe_last_success_timestamp_seconds{probe}`;
- `jobhunter_automation_codex_tokens_total{direction}`.

The state metric is one-hot: exactly one allowlisted state has value `1` for each
component and the others have value `0`. All labels use fixed allowlists. Runner
IDs, user IDs, domains, URLs, profile names, exception messages, model output, and
personal data are forbidden labels. Unknown reason codes collapse to `OTHER`.

## Alerts

Alerts apply only while the owner's automation delegation is enabled. Initial
rules are:

- warning: no fresh launcher heartbeat for 15 minutes;
- warning: a required deterministic component has not succeeded for 15 minutes;
- warning: Codex canary has failed twice consecutively or has no success within
  12 hours;
- warning: browser or Codex state is `AUTH_REQUIRED`;

Warnings use the existing private Telegram route. The first slice has no
submission boundary and therefore adds no new critical alert. A later slice adds
critical alerts for an active run with no durable progress and submit-fence
invariant violations, routed through the existing Telegram and Pushover path.

Rules retain existing grouping, inhibition, repeat, and `runbook_url` conventions.
The existing Alertmanager Watchdog remains the independent check that the alert
delivery path itself works.

## Failure behavior

- Job Hunter API or PostgreSQL unavailable: do not invoke Codex or start browser
  work; retain a bounded local diagnostic and retry the heartbeat with backoff.
  Existing API availability alerts cover a fully unavailable API, while the
  runner-heartbeat alert covers a runner that can no longer report.
- Chrome, profile, Playwright, or MCP unavailable: report a typed failure and
  remain non-ready.
- Site or Codex authentication unavailable: report `AUTH_REQUIRED`; never attempt
  credential recovery from model-visible code.
- VictoriaMetrics, Grafana, or Alertmanager unavailable: health reporting to Job
  Hunter continues. Monitoring failure never changes application state.
- Heartbeat report times out after the API may have committed it: retry with the
  same idempotency key.
- Runner restart: increment generation and replace the current instance snapshot;
  an older generation cannot overwrite it.

Every failure is fail-closed for future queue claims. Recovery is automatic after
the next successful fresh probe, except authentication states that require the
owner to sign in again.

## Verification

### Automation repository

- Unit-test state aggregation, freshness windows, timeouts, bounded retries,
  redaction, and JSONL summary parsing.
- Integration-test heartbeat idempotency against a fake API.
- Run Chrome and Playwright preflight against a repository-owned local fixture.
- Exercise MCP initialization and tool listing against test servers.
- Wrap `codex exec` in tests so failures and malformed output are deterministic;
  use the real runtime only in the LXD smoke test.

### Kotlin API

- Test owner access, non-owner denial, missing scopes, and the runner's restricted
  M2M identity.
- Test stale generation rejection, idempotent heartbeat retries, state precedence,
  and freshness derivation with the injected clock.
- Verify Flyway migration, persistence, REST DTOs, and bounded metric labels with
  integration tests.
- Prove public vacancy endpoints are unchanged.

### UI

- Test authenticated owner routing and non-owner denial.
- Test every state and missing/stale timestamps.
- Verify that raw error data and secrets cannot appear in the rendered response.

### Infrastructure and end-to-end

- Validate PrometheusRule syntax and add rule tests for healthy, pending, firing,
  and recovered states.
- Render infrastructure changes before deployment.
- In the dedicated LXD runner, verify a healthy heartbeat, browser preflight, MCP
  initialization, and one real minimal Codex canary.
- Trigger one controlled warning by suppressing a test heartbeat, verify private
  Telegram delivery and alert resolution, then restore the service. Do not trigger
  a critical page in this slice.
- Confirm the owner-only UI returns to `READY` and that no vacancy or application
  record changed during the entire verification.

## Rollout order

1. Create `job-hunter-automation` with probes and test packaging, but no external
   browser actions.
2. Add the API health snapshot, M2M endpoint, owner-only projection, and metrics.
3. Add and unit-test infrastructure alert rules and the initial Grafana panels.
4. Provision the dedicated LXD service and establish healthy deterministic
   heartbeats.
5. Enable the minimal Codex canary and verify bounded output handling.
6. Add the owner-only UI status surface.
7. Perform the controlled warning and recovery test.

Only after this slice remains healthy should the project design and implement due
run scheduling, application work claims, browser form observation, and submit
fencing.

## Rollback

Disable the automation delegation first, then stop and disable the LXD launcher.
Revert the UI, API, infrastructure, automation submodule, and parent gitlink
commits independently. The slice has no application workflow records or external
submission side effects. Existing scraping, matching, public vacancy pages, and
alerts remain operational throughout rollback.
