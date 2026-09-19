# Job Hunter

Job vacancy monitoring and tracking system. This repository coordinates the
Kotlin scraper, Kotlin API, React UI, and private
automation runtime.

This is a public portfolio project. Keep code, documentation, commits, and
architecture decisions at professional production quality.

## Working contract

- Read the affected submodule's repository instructions before changing it.
- Preserve cross-repository contracts when a change spans services.
- Keep changes atomic and use Conventional Commits.
- Do not add AI-generation references, `Co-Authored-By`, `Signed-off-by`, or similar
  attribution trailers to code, documentation, or commits.
- Use English for code, comments, commit messages, and repository documentation.
- Keep secrets in ignored environment files, secret stores, or Kubernetes Secrets.
- Keep every submodule README aligned with its architecture and quick-start flow.
- Avoid temporary workarounds, commented-out code, and unresolved TODO hacks on
  `master`.

## Components

- The Kotlin scraper owns stateless source adapters and bounded extraction. Its
  LinkedIn adapter uses a private JobSpy sidecar.
- `api/` owns PostgreSQL persistence, scraper schedules, fenced leases, criteria
  snapshots, checkpoints, idempotent ingest, matching, and Telegram delivery.
- `ui/` owns the React dashboard for exploring and managing vacancies.
- `automation/` owns browser execution, deterministic probes, and the bounded
  Codex readiness canary. It must not persist business workflow state.
- The infrastructure repository owns GitOps deployment, environment and secret
  delivery, the JobSpy sidecar, network policy, alerts, dashboards, and direct
  OTLP/HTTP trace export to VictoriaTraces.
- The API and PostgreSQL own all durable application, scraping, and automation
  workflow state.

The flow is source -> Kotlin scraper -> REST API -> PostgreSQL, Telegram,
and the web UI. The scraper is disabled by default and resumes only from API-owned
checkpoints. Keep one active run per source through API-owned leases. Private automation
reports health through the API and uses only explicit machine capabilities bound
to the configured owner.

## Submodules

Clone with:

```sh
git clone --recurse-submodules git@github.com:mshykhov/job-hunter.git
```

Update intentionally with `git submodule update --remote --merge`. When adding a
component, create its repository, add it as a submodule, commit the gitlink, and
update deployment configuration in the infrastructure repository when required.

## Agent configuration

`.rulesync/` is the canonical source. Generated instruction, rule, hook, and skill
files are derived outputs and must not be edited directly.

```sh
npm ci
npm run rulesync:dry-run
npm run rulesync:generate
npm run rulesync:verify
```
