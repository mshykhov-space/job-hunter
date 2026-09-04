# Job Hunter

Automated job vacancy monitoring and tracking system. It aggregates listings from
multiple platforms, filters by relevance, delivers them through Telegram, and
provides a web dashboard plus a private single-owner automation runtime.

## Architecture

```
┌─────────────┐   REST    ┌───────────────┐   health/MCP   ┌────────────────┐
│     n8n     │ ────────→ │  Kotlin API   │ ←───────────── │   Automation   │
│  (scraping) │           │  Spring Boot  │                │ private runner │
└─────────────┘           └───────┬───────┘                └────────────────┘
                                  │
                 ┌────────────────┼────────────────┐
                 ▼                ▼                ▼
          ┌────────────┐   ┌────────────┐   ┌────────────┐
          │ PostgreSQL │   │  Telegram  │   │  React UI  │
          └────────────┘   └────────────┘   └────────────┘

```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Scraping | [n8n](https://n8n.io/) (self-hosted) |
| Backend | Kotlin, Spring Boot 3 |
| Telegram | [telegram-bot](https://github.com/DEHuckaKpyT/telegram-bot) (Kotlin DSL) |
| Frontend | React, Vite |
| Automation | Node.js 24, TypeScript, Playwright, Codex CLI, MCP |
| Database | PostgreSQL |
| Deploy | Kubernetes, ArgoCD, Helm; dedicated LXD for automation |

## Project Structure

This is a monorepo that coordinates individual service repositories via Git submodules:

| Submodule | Repository | Description |
|-----------|------------|-------------|
| `n8n/` | [job-hunter-n8n](https://github.com/mshykhov/job-hunter-n8n) | Scraping workflows (DOU live, Djinni/LinkedIn/Google Jobs planned) |
| `api/` | [job-hunter-api](https://github.com/mshykhov/job-hunter-api) | Kotlin Spring Boot backend + Telegram bot |
| `ui/` | [job-hunter-ui](https://github.com/mshykhov/job-hunter-ui) | React web dashboard |
| `automation/` | [job-hunter-automation](https://github.com/mshykhov/job-hunter-automation) | Private execution runtime, deterministic health probes, and bounded Codex canary |

The automation repository owns execution only. The API and PostgreSQL remain the
durable policy and workflow boundary. The current automation slice provides health
reporting and a three-step synthetic recovery workflow with API-owned leases,
checkpoints, history, and owner controls. It does not read vacancy pages, fill forms,
or submit applications.

## Documentation

- [Repository documentation](docs/README.md)
- [Service boundaries](docs/architecture/service-boundaries.md)
- [Ordered automation roadmap](docs/backlog/automation-roadmap.md)

## Getting Started

```bash
# Clone with submodules
git clone --recurse-submodules git@github.com:mshykhov/job-hunter.git

# Start n8n locally
cd n8n
cp .env.example .env    # fill in values
docker compose up -d    # http://localhost:5678
```

## Features

- **Multi-source scraping** — DOU, Djinni, LinkedIn, Google Jobs (extensible)
- **Telegram notifications** — instant push with inline action buttons
- **Job tracking** — mark vacancies as Applied / Irrelevant
- **Web dashboard** — browse, filter, and manage job listings
- **Private automation health** — owner-only runner status, deterministic probes,
  Codex readiness canary, metrics, alerts, and Grafana dashboard
- **Durable recovery drills** — owner-only queue, progress, attempts, checkpoints,
  pause/resume/stop controls, restart recovery, and stalled-work alerting
- **Self-hosted** — runs on Kubernetes with GitOps (ArgoCD)

## Agent Configuration

`.rulesync/` is the canonical source for repository instructions and hooks.
`CLAUDE.md`, `AGENTS.md`, and tool-specific configuration are generated projections
and must not be edited directly.

```bash
npm ci
npm run rulesync:dry-run
npm run rulesync:generate
npm run rulesync:verify
```

## License

MIT
