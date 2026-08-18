# Automation Runner Health and Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a private single-owner Job Hunter automation runtime that continuously proves launcher, browser, MCP, Codex, API, and database readiness and alerts the owner when the chain fails, without reading vacancies or submitting applications.

**Architecture:** A new public `job-hunter-automation` TypeScript repository owns the LXD launcher, Browser Runner MCP, deterministic probes, and Codex canary. The existing Kotlin API owns the single-owner delegation, durable health snapshot, transition history, machine endpoints, Streamable HTTP MCP boundary, and metrics; the existing React UI shows an owner-only status page. Authentik, API deployment configuration, VictoriaMetrics alerts, Grafana, and LXD provisioning remain in the homelab infrastructure repositories.

**Tech Stack:** Node.js 24, TypeScript 5.9, Playwright 1.61, MCP TypeScript SDK 1.29, Vitest 4, Kotlin 2.1, Spring Boot 3.5, Spring AI 1.1.8, PostgreSQL 16, React 19, Ant Design 6, TanStack Query 5, Authentik Terraform, Helm, VictoriaMetrics, Alertmanager, Grafana, systemd, LXD.

**Design:** `docs/superpowers/specs/2026-08-18-automation-runner-health-design.md`

**Primary references:** [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference), [Playwright persistent contexts](https://playwright.dev/docs/api/class-browsertype#browser-type-launch-persistent-context), [MCP TypeScript client](https://github.com/modelcontextprotocol/typescript-sdk/blob/v1.29.0/docs/client.md), [Spring AI Streamable HTTP MCP server](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-streamable-http-server-boot-starter-docs.html).

---

## Repository and file map

| Repository | Responsibility | Main files |
|---|---|---|
| `job-hunter-automation` | Launcher, Browser Runner, probes, Codex JSONL parsing, systemd packaging | `src/domain/*`, `src/api/*`, `src/probes/*`, `src/browser-runner/*`, `src/codex/*`, `src/launcher.ts`, `packaging/*` |
| `job-hunter-api` | Owner delegation, runner session and heartbeat, state projection, MCP endpoint, metrics | `application/automation/*`, `api/rest/automation/*`, `infrastructure/automation/*`, `infrastructure/metrics/AutomationMetrics.kt`, `V26__add_automation_runner_health.sql` |
| `job-hunter-ui` | Owner-only Automation status route | `src/features/automation/*`, `src/app/routes.tsx`, `src/components/Layout/Sidebar.tsx` |
| `smhomelab-infrastructure` | Authentik identities/scopes, alert rules, dashboard, monitoring documentation | `terraform/authentik/config/{applications,groups}/*`, `manifests/monitoring/prometheus-rules/job-hunter-alerts.yaml`, `charts/grafana-dashboards/*` |
| `smhomelab-deploy` | API issuer, owner allowlist, and secret injection | `services/job-hunter-api/values*.yaml` |
| `job-hunter` | Automation submodule, root architecture, cross-repository verification | `.gitmodules`, `README.md`, `.rulesync/rules/repository.md`, `tests/test_automation_contract.py` |

## Fixed protocol vocabulary

Use these exact wire values in Kotlin and TypeScript:

```text
AutomationState: READY, DEGRADED, AUTH_REQUIRED, UNAVAILABLE
AutomationComponent: LAUNCHER, API, DATABASE, CHROME, PLAYWRIGHT, BROWSER_MCP, JOB_HUNTER_MCP, CODEX
ProbeType: HEARTBEAT, PREFLIGHT, CODEX
AutomationReason: NONE, API_UNAVAILABLE, DATABASE_UNAVAILABLE, CHROME_UNAVAILABLE,
  PROFILE_UNREADABLE, PLAYWRIGHT_UNAVAILABLE, MCP_UNAVAILABLE,
  CODEX_AUTH_REQUIRED, SITE_AUTH_REQUIRED, CANARY_FAILED, CLOCK_SKEW,
  STALE_GENERATION, INVALID_REPORT, OTHER
```

Heartbeat requests use a server-issued `generation`, monotonically increasing
`sequence`, and UUID `idempotencyKey`. They never contain `userId`, URLs, browser
content, exception text, credentials, prompts, or model output.

---

### Task 1: Prepare isolated workspaces and bootstrap `job-hunter-automation`

**Repositories:** `job-hunter`, `job-hunter-api`, `job-hunter-ui`, `smhomelab-infrastructure`, `smhomelab-deploy`, new `job-hunter-automation`

**Files:**
- Create: `/Users/myron/IdeaProjects/job-hunter-automation/package.json`
- Create: `/Users/myron/IdeaProjects/job-hunter-automation/package-lock.json`
- Create: `/Users/myron/IdeaProjects/job-hunter-automation/tsconfig.json`
- Create: `/Users/myron/IdeaProjects/job-hunter-automation/eslint.config.js`
- Create: `/Users/myron/IdeaProjects/job-hunter-automation/.prettierrc.json`
- Create: `/Users/myron/IdeaProjects/job-hunter-automation/.gitignore`
- Create through `bootstrap-agent-config`: `.rulesync/`, `rulesync.jsonc`, generated instructions, documentation indexes, README guidance, and CI checks

- [ ] **Step 1: Run the worktree preflight**

Invoke `superpowers:using-git-worktrees`. Preserve the existing untracked
`job-hunter/docs/ideas/` directory and the dirty `smhomelab-deploy` checkout.
Create clean feature worktrees from each upstream `master`; create the deploy
worktree from `origin/master`, not its behind local branch.

Run:

```bash
git -C /Users/myron/IdeaProjects/job-hunter fetch origin master
git -C /Users/myron/IdeaProjects/job-hunter/api fetch origin master
git -C /Users/myron/IdeaProjects/job-hunter/ui fetch origin master
git -C /Users/myron/IdeaProjects/smhomelab-infrastructure fetch origin master
git -C /Users/myron/IdeaProjects/smhomelab-deploy fetch origin master
```

Expected: all fetches succeed; the original deploy checkout remains unchanged.

- [ ] **Step 2: Create the public automation repository**

Run:

```bash
gh repo create mshykhov/job-hunter-automation \
  --public \
  --description "Private-runtime automation and browser execution layer for Job Hunter" \
  --clone
```

Expected: `/Users/myron/IdeaProjects/job-hunter-automation` exists with `origin`
pointing to `git@github.com:mshykhov/job-hunter-automation.git`.

- [ ] **Step 3: Bootstrap shared Rulesync configuration**

Invoke `bootstrap-agent-config` in shared-repository mode. The root rule must say
that this repository owns execution, keeps all durable workflow state in Job
Hunter API, never commits browser profiles or credentials, and uses English for
code and repository documentation.

Expected verification:

```bash
npm run rulesync:dry-run
npm run rulesync:generate
npm run rulesync:verify
```

Expected: frozen install, doctor, generated-file check, and hook tests pass.

- [ ] **Step 4: Add the TypeScript toolchain**

Set `package.json` to:

```json
{
  "name": "@mshykhov/job-hunter-automation",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "engines": { "node": ">=24" },
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "test": "vitest run",
    "lint": "eslint . --max-warnings 0",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "verify": "npm run lint && npm run format:check && npm test && npm run build",
    "rulesync:install": "rulesync install --config rulesync.jsonc --frozen",
    "rulesync:doctor": "rulesync doctor --config rulesync.jsonc --strict",
    "rulesync:dry-run": "rulesync generate --config rulesync.jsonc --input-root . --output-roots . --dry-run",
    "rulesync:generate": "rulesync generate --config rulesync.jsonc --input-root . --output-roots .",
    "rulesync:check": "rulesync generate --config rulesync.jsonc --input-root . --output-roots . --check",
    "rulesync:verify": "npm run rulesync:install && npm run rulesync:doctor && npm run rulesync:check"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "1.29.0",
    "playwright": "1.61.0",
    "zod": "3.25.76"
  },
  "devDependencies": {
    "@eslint/js": "9.39.1",
    "@types/node": "24.10.1",
    "eslint": "9.39.1",
    "prettier": "3.7.4",
    "rulesync": "16.7.0",
    "typescript": "5.9.3",
    "typescript-eslint": "8.48.0",
    "vitest": "4.0.18"
  }
}
```

Use strict ESM compilation to `dist/`, Node types, `noUncheckedIndexedAccess`,
and `exactOptionalPropertyTypes`. Generate the lock with `npm install`.

- [ ] **Step 5: Verify and commit the repository foundation**

Run:

```bash
npm run verify
npm run rulesync:verify
git add .
git commit -m "chore: bootstrap automation runtime"
git push -u origin master
```

Expected: all checks pass and local `master` equals `origin/master`.

---

### Task 2: Prove the embedded Streamable HTTP MCP boundary

**Repository:** `job-hunter-api`

**Files:**
- Modify: `build.gradle.kts`
- Modify: `src/main/resources/application.yml`
- Modify: `src/main/kotlin/com/mshykhov/jobhunter/infrastructure/security/SecurityConfig.kt`
- Modify: `src/main/kotlin/com/mshykhov/jobhunter/infrastructure/security/DevAuthenticationFilter.kt`
- Create: `src/test/kotlin/com/mshykhov/jobhunter/infrastructure/mcp/McpTransportIntegrationTest.kt`

- [ ] **Step 1: Write the failing MCP initialize test**

Create a Spring integration test that POSTs this JSON-RPC body to `/mcp` with
`Accept: application/json, text/event-stream`:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "clientInfo": { "name": "job-hunter-contract-test", "version": "1.0.0" }
  }
}
```

Assert HTTP 200, `$.result.serverInfo.name == "job-hunter"`, and a non-empty
protocol version.

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```bash
./gradlew test --tests '*McpTransportIntegrationTest'
```

Expected: FAIL because `/mcp` does not exist.

- [ ] **Step 3: Upgrade Spring AI and add the MCP server starter**

Change the BOM to `1.1.8` and add:

```kotlin
implementation("org.springframework.ai:spring-ai-starter-mcp-server-webmvc")
```

Configure:

```yaml
spring:
  ai:
    mcp:
      server:
        enabled: true
        protocol: STATELESS
        type: SYNC
        name: job-hunter
        version: ${BUILD_VERSION:dev}
        streamable-http:
          mcp-endpoint: /mcp
```

Protect `/mcp/**` before the catch-all matcher:

```kotlin
.requestMatchers("/mcp/**")
.hasAuthority("SCOPE_report:automation-health")
```

Extend the dev authentication with `report:automation-health` in this task so
local and integration clients use the same authority name. Task 4 adds the owner
read/write scopes.

- [ ] **Step 4: Prove compatibility with every existing AI use case**

Run:

```bash
./gradlew ktlintFormat
./gradlew test
./gradlew build
```

Expected: the MCP test and all existing provider, matching, outreach, and
settings tests pass. If the upgrade breaks an existing AI contract, stop and
revise the design instead of adding a sidecar implicitly.

- [ ] **Step 5: Commit the compatibility gate**

```bash
git add build.gradle.kts src/main/resources/application.yml src/main/kotlin src/test/kotlin
git commit -m "feat(automation): add streamable MCP transport"
```

---

### Task 3: Add the durable owner delegation and runner snapshot

**Repository:** `job-hunter-api`

**Files:**
- Create: `src/main/resources/db/migration/V26__add_automation_runner_health.sql`
- Create: `src/main/kotlin/com/mshykhov/jobhunter/application/automation/AutomationState.kt`
- Create: `src/main/kotlin/com/mshykhov/jobhunter/application/automation/AutomationComponent.kt`
- Create: `src/main/kotlin/com/mshykhov/jobhunter/application/automation/AutomationReason.kt`
- Create: `src/main/kotlin/com/mshykhov/jobhunter/application/automation/ProbeType.kt`
- Create: `src/main/kotlin/com/mshykhov/jobhunter/application/automation/AutomationComponentSnapshot.kt`
- Create: `src/main/kotlin/com/mshykhov/jobhunter/application/automation/AutomationDelegationEntity.kt`
- Create: `src/main/kotlin/com/mshykhov/jobhunter/application/automation/AutomationRunnerEntity.kt`
- Create: `src/main/kotlin/com/mshykhov/jobhunter/application/automation/AutomationRunnerTransitionEntity.kt`
- Create the three matching repositories and `AutomationFacade.kt`
- Modify: `src/test/kotlin/com/mshykhov/jobhunter/support/TestFixtures.kt`
- Create: `src/test/kotlin/com/mshykhov/jobhunter/application/automation/AutomationPersistenceIntegrationTest.kt`

- [ ] **Step 1: Write the failing persistence test**

Persist one delegation and runner with this component map:

```kotlin
mapOf(
    AutomationComponent.LAUNCHER to
        AutomationComponentSnapshot(
            state = AutomationState.READY,
            reason = AutomationReason.NONE,
            checkedAt = Instant.parse("2026-08-18T08:00:00Z"),
            probeVersion = "0.1.0",
        ),
)
```

Reload it, assert JSONB round-trip, assert one delegation per owner, and assert
one runner per delegation.

- [ ] **Step 2: Run the focused test and confirm RED**

```bash
./gradlew test --tests '*AutomationPersistenceIntegrationTest'
```

Expected: compilation fails because the automation model does not exist.

- [ ] **Step 3: Add the schema**

Create three tables:

```sql
CREATE TABLE automation_delegations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    owner_issuer VARCHAR(512) NOT NULL,
    owner_subject VARCHAR(512) NOT NULL,
    runner_issuer VARCHAR(512) NOT NULL,
    health_reporting_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    CONSTRAINT uk_automation_delegation_owner UNIQUE (owner_issuer, owner_subject)
);

CREATE TABLE automation_runners (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    delegation_id UUID NOT NULL UNIQUE REFERENCES automation_delegations(id),
    runner_key VARCHAR(64) NOT NULL UNIQUE,
    generation BIGINT NOT NULL DEFAULT 0,
    sequence BIGINT NOT NULL DEFAULT 0,
    last_idempotency_key UUID,
    launcher_version VARCHAR(64),
    overall_state VARCHAR(32) NOT NULL DEFAULT 'UNAVAILABLE',
    overall_reason VARCHAR(64) NOT NULL DEFAULT 'INVALID_REPORT',
    components JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_heartbeat_at TIMESTAMPTZ,
    last_preflight_success_at TIMESTAMPTZ,
    last_codex_success_at TIMESTAMPTZ,
    codex_input_tokens BIGINT NOT NULL DEFAULT 0,
    codex_output_tokens BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE automation_runner_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    runner_id UUID NOT NULL REFERENCES automation_runners(id),
    component VARCHAR(32) NOT NULL,
    from_state VARCHAR(32) NOT NULL,
    to_state VARCHAR(32) NOT NULL,
    reason VARCHAR(64) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    generation BIGINT NOT NULL,
    sequence BIGINT NOT NULL
);

CREATE INDEX idx_automation_runner_transitions_runner_time
    ON automation_runner_transitions(runner_id, occurred_at DESC);
```

- [ ] **Step 4: Implement entities and the thin facade**

Follow the existing UUID `Persistable` and auditing pattern. Store
`Map<AutomationComponent, AutomationComponentSnapshot>` with
`@JdbcTypeCode(SqlTypes.JSON)`. `AutomationFacade` owns transactions and exposes
only `findActiveDelegation`, `saveDelegation`, `findRunner`, `saveRunner`, and
`appendTransitions`.

- [ ] **Step 5: Run migration and persistence tests**

```bash
./gradlew ktlintFormat
./gradlew test --tests '*AutomationPersistenceIntegrationTest'
```

Expected: PASS with Flyway validation enabled.

- [ ] **Step 6: Commit the durable model**

```bash
git add src/main/resources/db/migration/V26__add_automation_runner_health.sql src/main/kotlin/com/mshykhov/jobhunter/application/automation src/test/kotlin
git commit -m "feat(automation): persist runner health state"
```

---

### Task 4: Add owner-only and runner-only API contracts

**Repository:** `job-hunter-api`

**Files:**
- Create: `src/main/kotlin/com/mshykhov/jobhunter/infrastructure/automation/AutomationProperties.kt`
- Create: `src/main/kotlin/com/mshykhov/jobhunter/infrastructure/automation/AutomationIdentityGuard.kt`
- Create: `src/main/kotlin/com/mshykhov/jobhunter/application/automation/AutomationHealthPolicy.kt`
- Create: `src/main/kotlin/com/mshykhov/jobhunter/application/automation/AutomationService.kt`
- Create: `src/main/kotlin/com/mshykhov/jobhunter/api/rest/automation/AutomationController.kt`
- Create: `src/main/kotlin/com/mshykhov/jobhunter/api/rest/automation/AutomationRunnerController.kt`
- Create DTO files under `api/rest/automation/dto/`
- Modify: `src/main/kotlin/com/mshykhov/jobhunter/infrastructure/security/DevAuthenticationFilter.kt`
- Modify: `src/main/resources/application.yml`
- Modify: `src/test/resources/application-test.yml`
- Create: `src/test/kotlin/com/mshykhov/jobhunter/application/automation/AutomationHealthPolicyTest.kt`
- Create: `src/test/kotlin/com/mshykhov/jobhunter/api/rest/automation/AutomationControllerIntegrationTest.kt`
- Create: `src/test/kotlin/com/mshykhov/jobhunter/api/rest/automation/AutomationRunnerControllerIntegrationTest.kt`

- [ ] **Step 1: Write state precedence and freshness tests**

Use the injected clock and assert:

```kotlin
assertEquals(AutomationState.AUTH_REQUIRED, policy.overallState(authRequiredComponents, now))
assertEquals(AutomationState.UNAVAILABLE, policy.overallState(staleComponents, now))
assertEquals(AutomationState.DEGRADED, policy.overallState(degradedComponents, now))
assertEquals(AutomationState.READY, policy.overallState(freshReadyComponents, now))
```

Set heartbeat freshness to two minutes, preflight freshness to ten minutes, and
Codex freshness to twelve hours. `READY` requires every component to be fresh.

- [ ] **Step 2: Write endpoint tests**

Cover these exact contracts:

```text
PUT    /automation/delegation       owner + write:automation
DELETE /automation/delegation       owner + write:automation
GET    /automation/status           owner + read:automation
POST   /automation/runner/session   runner issuer + report:automation-health
PUT    /automation/runner/heartbeat runner issuer + report:automation-health
```

Assert non-owner 403, missing scope 403, runner token on owner endpoint 403,
owner token on runner endpoint 403, stale generation 409, clock skew 400,
duplicate idempotency key returns the original response, and heartbeat payloads
cannot select a user.

- [ ] **Step 3: Run tests and confirm RED**

```bash
./gradlew test --tests '*AutomationHealthPolicyTest' --tests '*Automation*ControllerIntegrationTest'
```

Expected: compilation failures for the missing policy and endpoints.

- [ ] **Step 4: Implement configured identity binding**

Use this property model:

```kotlin
@ConfigurationProperties(prefix = "jobhunter.automation")
data class AutomationProperties(
    val enabled: Boolean = false,
    val ownerIssuer: String = "",
    val ownerSubject: String = "",
    val runnerIssuer: String = "",
    val heartbeatFreshness: Duration = Duration.ofMinutes(2),
    val preflightFreshness: Duration = Duration.ofMinutes(10),
    val codexFreshness: Duration = Duration.ofHours(12),
    val maxClockSkew: Duration = Duration.ofMinutes(1),
)
```

The owner guard compares `jwt.issuer.toString()` and `jwt.subject` in constant
time after length equality. The runner guard compares the dedicated issuer and
requires `SCOPE_report:automation-health`. Neither guard accepts identity fields
from a request body.

- [ ] **Step 5: Implement session and heartbeat semantics**

`startSession` atomically increments `generation`, resets `sequence`, and returns:

```json
{
  "runnerKey": "primary",
  "generation": 4,
  "heartbeatIntervalSeconds": 60,
  "preflightIntervalSeconds": 300,
  "codexCanaryIntervalSeconds": 21600
}
```

`recordHeartbeat` locks the runner row, checks generation, sequence, clock skew,
and idempotency, replaces the snapshot, and appends transition rows only for
state changes. It returns the server-derived overall state and accepted sequence.

- [ ] **Step 6: Extend dev and test authentication**

Set the dev JWT issuer to `http://localhost/dev` and add these scopes:

```text
read:automation
write:automation
report:automation-health
```

Set test owner and runner issuer properties to `http://localhost/dev` and owner
subject to `local-dev-user`.

- [ ] **Step 7: Verify and commit the APIs**

```bash
./gradlew ktlintFormat
./gradlew test --tests '*Automation*'
./gradlew test
git add src/main src/test
git commit -m "feat(automation): add private runner health API"
```

Expected: all tests pass and `/public/**` behavior is unchanged.

---

### Task 5: Export bounded automation metrics

**Repository:** `job-hunter-api`

**Files:**
- Create: `src/main/kotlin/com/mshykhov/jobhunter/infrastructure/metrics/AutomationMetrics.kt`
- Create: `src/test/kotlin/com/mshykhov/jobhunter/infrastructure/metrics/AutomationMetricsTest.kt`
- Modify: `src/main/kotlin/com/mshykhov/jobhunter/application/automation/AutomationService.kt`

- [ ] **Step 1: Write metric-name and cardinality tests**

Use `SimpleMeterRegistry` and assert the exact Micrometer names:

```text
jobhunter.automation.enabled
jobhunter.automation.runner.last.heartbeat
jobhunter.automation.component.state
jobhunter.automation.probe
jobhunter.automation.probe.duration
jobhunter.automation.probe.consecutive.failures
jobhunter.automation.probe.last.success
jobhunter.automation.codex.tokens
```

Assert component, state, probe, outcome, reason, and direction values come only
from enum allowlists; an unknown inbound reason becomes `OTHER`.

- [ ] **Step 2: Run the test and confirm RED**

```bash
./gradlew test --tests '*AutomationMetricsTest'
```

Expected: FAIL because `AutomationMetrics` is missing.

- [ ] **Step 3: Implement metrics with idempotent recording**

Register timestamp/state/failure gauges from atomic values restored from the
current runner snapshot on application startup. Increment probe and token
counters only after a new heartbeat sequence commits; duplicate idempotency
responses do not increment counters.

Prometheus exposition must produce:

```text
jobhunter_automation_enabled
jobhunter_automation_runner_last_heartbeat_timestamp_seconds
jobhunter_automation_component_state{component="CODEX",state="READY"}
jobhunter_automation_probe_total{probe="CODEX",outcome="SUCCESS",reason="NONE"}
jobhunter_automation_probe_duration_seconds
jobhunter_automation_probe_consecutive_failures{probe="CODEX"}
jobhunter_automation_probe_last_success_timestamp_seconds{probe="CODEX"}
jobhunter_automation_codex_tokens_total{direction="INPUT"}
```

- [ ] **Step 4: Verify and commit metrics**

```bash
./gradlew ktlintFormat
./gradlew test --tests '*AutomationMetricsTest' --tests '*Automation*ControllerIntegrationTest'
git add src/main/kotlin/com/mshykhov/jobhunter/infrastructure/metrics src/main/kotlin/com/mshykhov/jobhunter/application/automation src/test
git commit -m "feat(automation): expose runner health metrics"
```

---

### Task 6: Implement the automation protocol client and heartbeat loop

**Repository:** `job-hunter-automation`

**Files:**
- Create: `src/domain/health.ts`
- Create: `src/config.ts`
- Create: `src/api/token-provider.ts`
- Create: `src/api/job-hunter-client.ts`
- Create: `src/runner/health-aggregate.ts`
- Create: `src/runner/heartbeat-loop.ts`
- Create tests mirroring each source file
- Create: `test/fixtures/heartbeat-v1.json`

- [ ] **Step 1: Write health aggregation tests**

Define discriminated results and assert precedence:

```typescript
export type AutomationState = "READY" | "DEGRADED" | "AUTH_REQUIRED" | "UNAVAILABLE";
export type AutomationComponent =
  | "LAUNCHER" | "API" | "DATABASE" | "CHROME"
  | "PLAYWRIGHT" | "BROWSER_MCP" | "JOB_HUNTER_MCP" | "CODEX";

expect(aggregate(readyResults, now)).toBe("READY");
expect(aggregate(authResults, now)).toBe("AUTH_REQUIRED");
expect(aggregate(staleResults, now)).toBe("UNAVAILABLE");
expect(aggregate(degradedResults, now)).toBe("DEGRADED");
```

- [ ] **Step 2: Write token and heartbeat client tests**

Mock native `fetch` and prove token caching uses `expires_in - 120` seconds,
runner sessions are restarted on stale generation, 401 clears the token cache,
and heartbeat retry reuses the same idempotency key and sequence.

- [ ] **Step 3: Run tests and confirm RED**

```bash
npm test -- health-aggregate token-provider job-hunter-client heartbeat-loop
```

Expected: test files fail to import missing implementations.

- [ ] **Step 4: Implement configuration validation**

Require these environment variable names without logging their values:

```text
JOB_HUNTER_API_URL
AUTHENTIK_TOKEN_URL
AUTOMATION_M2M_CLIENT_ID
AUTOMATION_M2M_USERNAME
AUTOMATION_M2M_PASSWORD
BROWSER_PROFILE_DIR
CODEX_HOME
```

Default heartbeat, preflight, and Codex intervals to 60, 300, and 21600 seconds.
Reject non-HTTPS remote URLs except loopback test URLs.

- [ ] **Step 5: Implement token acquisition and the typed API client**

POST form-encoded credentials exactly as the existing n8n M2M flow does:

```text
grant_type=client_credentials
client_id=${AUTOMATION_M2M_CLIENT_ID}
username=${AUTOMATION_M2M_USERNAME}
password=${AUTOMATION_M2M_PASSWORD}
scope=profile job-hunter-api
```

Keep access tokens in memory only. Redact `authorization`, `password`, `token`,
and `cookie` keys recursively before structured logging.

- [ ] **Step 6: Implement the serialized heartbeat loop**

Start a server session, run the API probe first, skip browser and Codex work when
the API probe fails, serialize probes with one in-process mutex, and use bounded
exponential backoff of 5, 15, 30, and 60 seconds. A successful report resets the
backoff.

- [ ] **Step 7: Verify and commit the core runtime**

```bash
npm run format
npm run verify
git add src test package.json package-lock.json
git commit -m "feat: add authenticated runner heartbeat"
git push origin master
```

---

### Task 7: Add Browser Runner MCP and deterministic preflight

**Repository:** `job-hunter-automation`

**Files:**
- Create: `src/browser-runner/browser-controller.ts`
- Create: `src/browser-runner/server.ts`
- Create: `src/probes/browser-probe.ts`
- Create: `src/probes/mcp-probe.ts`
- Create: `src/probes/preflight.ts`
- Create tests under `src/**/__tests__/`

- [ ] **Step 1: Write persistent-profile and redaction tests**

Mock Playwright and assert `chromium.launchPersistentContext` receives a
dedicated configured directory, `channel: "chrome"`, and `headless: false`.
Assert the preflight result contains only component, state, reason, checkedAt,
durationMs, and probeVersion.

- [ ] **Step 2: Write MCP transport tests**

Start Browser Runner through `StdioClientTransport`, connect an MCP `Client`, and
assert `listTools()` contains only `browser_preflight` in this slice. Start a
test Streamable HTTP server and assert the Job Hunter probe connects, reads
server version/capabilities, lists tools, and closes the client.

- [ ] **Step 3: Run tests and confirm RED**

```bash
npm test -- browser-controller browser-probe mcp-probe preflight
```

Expected: missing module failures.

- [ ] **Step 4: Implement the persistent Browser Controller**

Launch one context with:

```typescript
const context = await chromium.launchPersistentContext(profileDir, {
  channel: "chrome",
  headless: false,
  viewport: { width: 1280, height: 900 },
});
```

Reject the operating system's default Chrome profile path. The preflight creates
a page, uses `page.setContent("<main data-health='ready'>ready</main>")`, asserts
the marker, closes only the page, and keeps the persistent context alive.

- [ ] **Step 5: Implement Browser Runner MCP**

Register `browser_preflight` with an empty Zod input object and a fixed structured
result. Connect the server through `StdioServerTransport`. Do not register
navigation, form, upload, or submit tools.

- [ ] **Step 6: Implement deterministic MCP probes**

Use `StdioClientTransport` for Browser Runner and
`StreamableHTTPClientTransport` with an Authorization request header for Job
Hunter. Call `connect()`, inspect server capabilities, call `listTools()`, and
always close clients in `finally`.

- [ ] **Step 7: Verify and commit browser readiness**

```bash
npx playwright install chrome
npm run verify
git add src package.json package-lock.json
git commit -m "feat: add browser and MCP preflight"
git push origin master
```

---

### Task 8: Add the minimal Codex canary and hardened systemd package

**Repository:** `job-hunter-automation`

**Files:**
- Create: `src/codex/jsonl-parser.ts`
- Create: `src/codex/codex-probe.ts`
- Create: `src/launcher.ts`
- Create: `packaging/automation-canary.config.toml`
- Create: `packaging/job-hunter-automation.service`
- Create: `packaging/runner.env.example`
- Create: `packaging/install.sh`
- Create: `packaging/versions.env`
- Create unit tests for parser, command construction, signal handling, and service lifecycle

- [ ] **Step 1: Write JSONL parser tests**

Feed `thread.started`, `turn.started`, `item.completed`, `turn.completed`,
`turn.failed`, malformed JSON, and an oversized line. Assert only this summary is
returned:

```typescript
interface CodexCanarySummary {
  state: "READY" | "DEGRADED" | "AUTH_REQUIRED";
  reason: "NONE" | "CODEX_AUTH_REQUIRED" | "CANARY_FAILED";
  inputTokens: number;
  outputTokens: number;
  durationMs: number;
}
```

No agent text, prompt, tool payload, or thread ID may survive parsing.

- [ ] **Step 2: Write command-construction and timeout tests**

Assert the exact argument vector:

```text
codex exec --profile automation-canary --ephemeral --json --sandbox read-only
  -C /var/lib/job-hunter-automation/canary-workspace
  Return exactly AUTOMATION_CANARY_READY. Do not call tools.
```

Assert `JOB_HUNTER_MCP_TOKEN` is present only in the child environment, stdout is
parsed in memory, stderr is capped, and timeout terminates the process group.

- [ ] **Step 3: Run tests and confirm RED**

```bash
npm test -- jsonl-parser codex-probe launcher
```

Expected: missing module failures.

- [ ] **Step 4: Implement the canary profile**

Use:

```toml
approval_policy = "never"
sandbox_mode = "read-only"
cli_auth_credentials_store = "file"
web_search = "disabled"

[mcp_servers.job_hunter]
url = "https://api-jobhunter.gaynance.com/mcp"
bearer_token_env_var = "JOB_HUNTER_MCP_TOKEN"
enabled = true
required = true

[mcp_servers.browser_runner]
command = "/usr/bin/node"
args = ["/opt/job-hunter-automation/dist/browser-runner/server.js"]
enabled = true
required = true
```

- [ ] **Step 5: Implement launcher lifecycle**

Handle `SIGTERM` and `SIGINT`, stop scheduling new probes, allow the current
heartbeat up to ten seconds, close an active Browser Runner child, and exit. The
same in-process mutex must serialize deterministic preflight and Codex canary so
only one process can own `BROWSER_PROFILE_DIR`. Each stdio Browser Runner process
opens a persistent Playwright context for its probe or canary and closes it on
exit; the profile persists on disk between processes. Do not write raw Codex
JSONL to journald or disk.

- [ ] **Step 6: Add systemd hardening**

The launcher unit runs as `job-hunter-automation`, uses `NoNewPrivileges=true`,
`PrivateTmp=true`, `ProtectSystem=strict`, `ProtectHome=true`, and writable paths
only for `/var/lib/job-hunter-automation` and the dedicated browser profile. The
unit provides `DISPLAY=:99`; Browser Runner inherits it when launched over stdio.
The launcher depends on network-online and restarts with a bounded delay.

Pin in `packaging/versions.env`:

```text
NODE_MAJOR=24
CODEX_VERSION=0.147.0
PLAYWRIGHT_VERSION=1.61.0
```

- [ ] **Step 7: Verify and commit the canary package**

```bash
npm run verify
systemd-analyze verify packaging/job-hunter-automation.service
git add src packaging
git commit -m "feat: add Codex readiness canary"
git push origin master
```

---

### Task 9: Provision dedicated Authentik identities and API secrets

**Repositories:** `smhomelab-infrastructure`, `smhomelab-deploy`

**Infrastructure files:**
- Create: `terraform/authentik/config/applications/job-hunter-automation-m2m.yaml`
- Create: `terraform/authentik/config/groups/job-hunter-automation-m2m.yaml`
- Modify: `terraform/authentik/config/groups/job-hunter-user.yaml`
- Create: `docs/plan/000062-PLAN-job-hunter-automation-health-000000.md`

**Deploy files:**
- Modify: `services/job-hunter-api/values.yaml`
- Modify: `services/job-hunter-api/values-prd.yaml`
- Create: `docs/plan/000005-PLAN-job-hunter-automation-health-000000.md`

- [ ] **Step 1: Add Authentik permission groups**

Add to `job-hunter-user`:

```yaml
    - read:automation
    - write:automation
```

Create the runner group:

```yaml
name: job-hunter-automation-m2m
description: Job Hunter automation runner
attributes:
  permissions:
    - report:automation-health
```

- [ ] **Step 2: Add the dedicated M2M application**

Use this configuration:

```yaml
name: job-hunter-automation-m2m
client_type: confidential
access_token_validity: hours=1
grant_types:
  - client_credentials
custom_scopes:
  - job-hunter-api
service_account:
  username: svc-job-hunter-automation-m2m
  groups:
    - job-hunter-automation-m2m
doppler:
  project: smhomelub
  config: prd
  prefix: JOB_HUNTER_AUTOMATION_M2M
  write:
    - client_id
    - username
    - password
    - issuer_url
```

- [ ] **Step 3: Validate Terraform without applying locally**

```bash
cd terraform/authentik
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
terraform plan -refresh=false
```

Expected: the plan creates one provider, application, service account, app
password, group, memberships, and four Doppler secrets. Commit and push; only the
existing GitHub Actions workflow may apply Terraform.

```bash
git add terraform/authentik docs/plan
git commit -m "feat(authentik): add job hunter automation identity"
git push origin master
```

- [ ] **Step 4: Inject owner and runner configuration into the API chart**

Add secret mappings in base values:

```yaml
    - secretKey: AUTOMATION_OWNER_ISSUER
      remoteKey: JOB_HUNTER_AUTOMATION_OWNER_ISSUER
    - secretKey: AUTOMATION_OWNER_SUBJECT
      remoteKey: JOB_HUNTER_AUTOMATION_OWNER_SUBJECT
    - secretKey: AUTOMATION_RUNNER_ISSUER
      remoteKey: JOB_HUNTER_AUTOMATION_M2M_AUTHENTIK_ISSUER_URL
```

Add production env references and append the automation issuer to
`OIDC_ISSUERS`. Set `AUTOMATION_ENABLED=true`.

- [ ] **Step 5: Store the owner allowlist without printing it**

Read the sole active Job Hunter user's subject into a shell variable from the
primary CNPG pod, verify the query returns exactly one non-empty row, then write
issuer and subject to Doppler through stdin. Never echo either value.

```bash
automation_owner_issuer='https://auth.gaynance.com/application/o/job-hunter-ui/'
automation_db_pod="$(kubectl -n job-hunter-api-prd get pods \
  -l 'cnpg.io/cluster=job-hunter-api-main-db-prd-cluster,role=primary' \
  -o jsonpath='{.items[0].metadata.name}')"
test -n "$automation_db_pod"
automation_owner_subject="$({
  kubectl -n job-hunter-api-prd exec \
    "$automation_db_pod" -- \
    psql -U jobhunter -d jobhunter -Atc \
    "SELECT auth0_sub FROM users ORDER BY id LIMIT 2"
})"
test -n "$automation_owner_subject"
test "$(printf '%s\n' "$automation_owner_subject" | wc -l | tr -d ' ')" = 1
printf '%s' "$automation_owner_issuer" | doppler secrets set --project smhomelub --config prd JOB_HUNTER_AUTOMATION_OWNER_ISSUER >/dev/null
printf '%s' "$automation_owner_subject" | doppler secrets set --project smhomelub --config prd JOB_HUNTER_AUTOMATION_OWNER_SUBJECT >/dev/null
doppler secrets get --project smhomelub --config prd --only-names | rg '^JOB_HUNTER_AUTOMATION_(OWNER|M2M)'
unset automation_db_pod automation_owner_issuer automation_owner_subject
```

Expected: only secret names are printed.

- [ ] **Step 6: Render and commit deploy configuration**

```bash
cd services/job-hunter-api
helm dependency update
helm template job-hunter-api . -f values.yaml -f values-prd.yaml >/tmp/job-hunter-api-rendered.yaml
rg 'AUTOMATION_|job-hunter-automation-m2m' /tmp/job-hunter-api-rendered.yaml
git add services/job-hunter-api docs/plan
git commit -m "feat(job-hunter-api): configure automation identity"
git push origin master
```

Expected: rendered output contains secret references and environment names, not
secret values.

---

### Task 10: Add the owner-only Automation UI

**Repository:** `job-hunter-ui`

**Files:**
- Create: `src/features/automation/types.ts`
- Create: `src/features/automation/hooks/useAutomationStatus.ts`
- Create: `src/features/automation/components/AutomationStatusCard.tsx`
- Create: `src/features/automation/components/AutomationPage.tsx`
- Create tests under `src/features/automation/components/__tests__/`
- Modify: `src/app/routes.tsx`
- Modify: `src/components/Layout/Sidebar.tsx`
- Modify: `src/hooks/useAuth.ts`
- Modify: `src/lib/api.ts`
- Modify: `src/mocks/handlers.ts`

- [ ] **Step 1: Write route and rendering tests**

Test `READY`, `DEGRADED`, `AUTH_REQUIRED`, `UNAVAILABLE`, missing heartbeat,
loading, 403, and sanitized reason rendering. Assert the Automation menu item is
absent without `read:automation` and the route redirects through `ProtectedRoute`.

- [ ] **Step 2: Run tests and confirm RED**

```bash
npm test -- automation
```

Expected: missing module failures.

- [ ] **Step 3: Add typed query and permission**

Add:

```typescript
READ_AUTOMATION: "read:automation"
```

and:

```typescript
AUTOMATION_STATUS: "/automation/status"
```

Use TanStack Query with key `['automation', 'status']`, a 30-second refetch
interval, and no local copy of server state.

- [ ] **Step 4: Build the status page**

Render one overall `Alert`, component cards keyed by component name, last
heartbeat/preflight/Codex timestamps, launcher version, and bounded reason code.
Do not render runner IDs, owner identity, raw errors, URLs, or credentials.

- [ ] **Step 5: Wire route and navigation**

Add protected `/automation` and a `RobotOutlined` sidebar item visible only with
`read:automation`. Preserve `/explore` as public.

- [ ] **Step 6: Verify desktop and mobile UI**

```bash
npm run format
npm run lint
npm test
npm run build
```

Use the browser at 1280x900 and 390x844. Expected: no horizontal overflow,
readable state cards, and no Automation navigation for a token without the scope.

- [ ] **Step 7: Commit the UI**

```bash
git add src
git commit -m "feat(automation): show private runner status"
```

---

### Task 11: Add tested alerts and the Job Hunter Automation dashboard

**Repository:** `smhomelab-infrastructure`

**Files:**
- Modify: `manifests/monitoring/prometheus-rules/job-hunter-alerts.yaml`
- Create: `tests/prometheus/job-hunter-automation.test.yaml`
- Create: `scripts/prometheus-rule-test.py`
- Modify: `.github/workflows/validate.yml`
- Create: `charts/grafana-dashboards/dashboards/applications/job-hunter-automation.json`
- Create: `charts/grafana-dashboards/templates/applications.yaml`
- Modify: `charts/grafana-dashboards/values.yaml`
- Modify: `docs/architecture/observability.md`

- [ ] **Step 1: Prove every source metric exists before writing rules**

After the API deployment reaches production, query VictoriaMetrics through its
specialized MCP first. Confirm one series for every metric listed in Task 5 and
record the observed labels. Do not add alert expressions against an absent metric.

- [ ] **Step 2: Write failing alert-rule tests**

Cover healthy, heartbeat stale at 16 minutes, component unready for 15 minutes,
`AUTH_REQUIRED`, two consecutive Codex failures, Codex success older than 12
hours, automation disabled, and recovery. Expected alerts:

```text
JobHunterAutomationRunnerHeartbeatStale
JobHunterAutomationComponentUnavailable
JobHunterAutomationAuthenticationRequired
JobHunterAutomationCodexCanaryFailed
JobHunterAutomationCodexCanaryStale
```

- [ ] **Step 3: Add pinned `promtool` validation**

Pin Prometheus `3.13.1` and Linux amd64 SHA-256
`962b812371aff838d152b6ff2d56fdb7a6396f5542f48ebf73421b9721f0d103`
in the validation workflow. `scripts/prometheus-rule-test.py` extracts
`spec.groups` from the PrometheusRule into a temporary plain rules file and
runs both `promtool check rules` and `promtool test rules`.

- [ ] **Step 4: Run tests and confirm RED**

```bash
python3 scripts/prometheus-rule-test.py \
  manifests/monitoring/prometheus-rules/job-hunter-alerts.yaml \
  tests/prometheus/job-hunter-automation.test.yaml
```

Expected: FAIL because the five alert rules are missing.

- [ ] **Step 5: Add warning rules**

Gate every expression with `jobhunter_automation_enabled == 1`. Use bounded
labels only, `severity: warning`, the existing runbook URL, and the thresholds
from the approved design. Preserve existing group and inhibition conventions.

- [ ] **Step 6: Add the dashboard**

Enable the `Applications` category and add panels for overall state, heartbeat
age, component state, probe success/failure, probe duration, consecutive
failures, last successful probes, and Codex tokens. Use UID
`job-hunter-automation`; include no user, runner, URL, company, or profile
variables.

- [ ] **Step 7: Validate infrastructure and commit**

```bash
python3 scripts/prometheus-rule-test.py manifests/monitoring/prometheus-rules/job-hunter-alerts.yaml tests/prometheus/job-hunter-automation.test.yaml
./scripts/render-check.sh rendered
./scripts/manifest-check.sh rendered
helm template job-hunter-automation charts/grafana-dashboards | rg 'job-hunter-automation'
git add .github/workflows/validate.yml scripts tests manifests/monitoring/prometheus-rules/job-hunter-alerts.yaml charts/grafana-dashboards docs/architecture/observability.md
git commit -m "feat(monitoring): alert on automation runner health"
git push origin master
```

---

### Task 12: Provision and deploy the dedicated LXD runner

**Repositories:** `job-hunter-automation`, operational LXD host

**Files on host:**
- `/opt/job-hunter-automation/`
- `/etc/job-hunter-automation/runner.env`
- `/var/lib/job-hunter-automation/codex/`
- `/var/lib/job-hunter-automation/chrome-profile/`
- `/var/lib/job-hunter-automation/canary-workspace/`
- `/etc/systemd/system/job-hunter-automation.service`

- [ ] **Step 1: Capture host and LXD capacity before mutation**

Run read-only checks for host memory/disk, k3s allocatable, current LXD limits,
and the 30-day LXD CPU/memory baseline. Create a recoverable host-side snapshot
or record that no `job-hunter-automation` instance exists.

- [ ] **Step 2: Create the isolated instance**

Start with:

```bash
lxc launch ubuntu:24.04 job-hunter-automation \
  -c limits.cpu=2 \
  -c limits.memory=4GiB \
  -c limits.memory.swap=false
lxc config device override job-hunter-automation root size=30GiB
```

Expose no public proxy device. Verify the instance can reach Authentik and the
public Job Hunter API but cannot reach protected cluster services directly.

- [ ] **Step 3: Install the runtime**

Run `packaging/install.sh` through `lxc exec`. It creates the non-login service
user, installs Node.js 24, `@openai/codex@0.147.0`, Xvfb, Google Chrome through
Playwright 1.61, clones the pinned automation commit, runs `npm ci && npm run
build`, creates the dedicated profile/workspace directories, and installs the
launcher systemd unit. The script must be idempotent and never enable the service before
configuration exists.

- [ ] **Step 4: Deliver runtime secrets without printing them**

Read the four `JOB_HUNTER_AUTOMATION_M2M_AUTHENTIK_*` values from Doppler into
shell variables, render the root-owned environment file with mode 0600, push it
through `lxc file push`, then unset variables and remove the local temporary file.
Verify only file ownership, mode, and variable names.

- [ ] **Step 5: Complete one-time Codex login**

Run as the service account with `CODEX_HOME=/var/lib/job-hunter-automation/codex`
and complete the official device login. Set the directory to mode 0700 and
`auth.json` to 0600. Do not copy or display its content.

- [ ] **Step 6: Start and inspect services**

```bash
systemctl daemon-reload
systemctl enable --now job-hunter-automation.service
systemctl --no-pager --full status job-hunter-automation.service
journalctl -u job-hunter-automation.service --since '-10 minutes' --no-pager
```

Expected: services are active, logs contain only bounded reason codes and timings,
and the API reports a fresh heartbeat. Inspect journald for token-, cookie-, URL-,
prompt-, and model-text leakage.

- [ ] **Step 7: Measure the real baseline**

Observe one browser preflight and one Codex canary. Record peak RSS, CPU, rootfs,
profile size, and run duration. Change the initial LXD limits only if measured
headroom is insufficient and document the evidence.

---

### Task 13: Integrate the automation submodule and repository documentation

**Repository:** `job-hunter`

**Files:**
- Modify: `.gitmodules`
- Add gitlink: `automation/`
- Modify: `.rulesync/rules/repository.md`
- Modify generated: `AGENTS.md`, `CLAUDE.md`
- Modify: `README.md`
- Create: `tests/test_automation_contract.py`

- [ ] **Step 1: Add the pushed automation repository as a submodule**

```bash
git submodule add git@github.com:mshykhov/job-hunter-automation.git automation
git -C automation rev-parse HEAD
git -C automation rev-parse origin/master
```

Expected: both revisions match.

- [ ] **Step 2: Update canonical root documentation**

Add `automation/` to the component map and architecture flow. State that API and
PostgreSQL own durable automation state while the automation repo owns execution.
Update README cloning, project structure, tech stack, and health/canary status.

- [ ] **Step 3: Add a cross-repository contract guard**

The Python test loads the API enum source names and the TypeScript union literals
and asserts both contain the exact fixed protocol vocabulary at the top of this
plan. It also asserts `.gitmodules` points to the expected public GitHub repository.

- [ ] **Step 4: Generate and verify root instructions**

```bash
npm ci
npm run rulesync:dry-run
npm run rulesync:generate
npm run rulesync:verify
python3 -m unittest tests/test_automation_contract.py
```

Expected: generation is clean and the contract guard passes.

- [ ] **Step 5: Commit parent integration**

```bash
git add .gitmodules automation .rulesync/rules/repository.md AGENTS.md CLAUDE.md README.md tests/test_automation_contract.py
git commit -m "feat: add automation runtime component"
```

---

### Task 14: Execute full verification, controlled alert test, and delivery

**Repositories:** all six repositories

- [ ] **Step 1: Run every repository gate from clean worktrees**

```bash
git -C api status --short
git -C ui status --short
git -C automation status --short
./api/gradlew -p api build
npm --prefix ui run lint
npm --prefix ui test
npm --prefix ui run build
npm --prefix automation run verify
npm run rulesync:verify
```

Run infrastructure render, manifest, Terraform validation, alert tests, and the
deploy Helm render again. Expected: all commands pass and only intended commits
are present.

- [ ] **Step 2: Push service repositories before parent gitlinks**

Push API, UI, automation, infrastructure, and deploy branches without force.
Verify every local head exists upstream. Update API and UI gitlinks in the parent
only after their commits are upstream, then commit the gitlink update separately.

- [ ] **Step 3: Verify GitOps rollout**

Wait for Authentik Terraform CI and Argo CD. Read-only checks must show API/UI
applications Synced/Healthy, the API pod ready, Flyway V26 applied, `/mcp`
authenticated, and the Automation page available only to the owner.

Using the live logged-in owner browser, open the API Swagger UI, complete its
OIDC authorization, and execute `PUT /automation/delegation` once. Do not copy or
print the access token. Verify the response binds the configured owner and runner
issuers, then poll `GET /automation/status` until the first runner heartbeat is
fresh. A different logged-in user must receive 403 for both calls.

- [ ] **Step 4: Verify live metrics and rules**

Use VictoriaMetrics and Grafana specialized tools first. Confirm all automation
metrics have current samples, the five rules are operational in vmalert, and the
dashboard panels return data. Confirm no forbidden high-cardinality or personal
labels exist.

- [ ] **Step 5: Perform the controlled warning test**

Stop only `job-hunter-automation.service`, leaving API and Alertmanager healthy.
Poll the rule until `JobHunterAutomationRunnerHeartbeatStale` moves pending then
firing; do not use one blocking sleep. Confirm the private Telegram warning
arrives. Restart the service, verify a new heartbeat, and poll until the alert
resolves. Do not trigger a critical route.

- [ ] **Step 6: Prove zero application side effects**

Compare vacancy/application counts and latest mutation timestamps from before and
after the smoke test. Expected: no vacancy queue was read, no job status changed,
and no external application request occurred.

- [ ] **Step 7: Push the parent repository and record delivery state**

```bash
git push origin master
git rev-parse HEAD
git rev-parse origin/master
git status --short --branch
```

Expected: local and upstream parent revisions match. The completion report must
separately list work completed, commits created, pushes completed, live rollout
state, controlled alert evidence, and any manual Codex/browser authentication
that remains.

---

## Rollback order

1. Disable the owner automation delegation through the owner-only API.
2. Stop and disable the LXD launcher service.
3. Revert UI and API deployment gitlinks and let Argo CD restore prior versions.
4. Revert alert/dashboard changes, then Authentik/deploy configuration.
5. Revert the parent automation gitlink last.
6. Keep the LXD instance stopped until evidence and browser profile data are
   either recovered or deliberately removed through a separate approved action.

No rollback step changes existing n8n scraping, matching, public vacancy pages,
or historical Job Hunter data.
