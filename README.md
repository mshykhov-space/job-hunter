# Job Hunter

Automated job vacancy monitoring and tracking system. Aggregates listings from multiple platforms, filters by relevance, and delivers them via Telegram bot with a web dashboard for management.

## Architecture

```
┌─────────────┐   REST    ┌───────────────┐
│     n8n     │ ────────→ │  Kotlin API   │
│  (scraping) │           │  Spring Boot  │
│             │           │               │
│ • DOU RSS   │           │ • REST API    │
│ • Djinni †  │           │ • Telegram Bot│
│ • LinkedIn †│           │ • Job Dedup   │
│ • Google †  │           │               │
└─────────────┘           └───────┬───────┘
                                  │
                           ┌──────┴──────┐
                           │ PostgreSQL  │
                           └──────┬──────┘
                                  │
                           ┌──────┴──────┐
                           │  React UI   │
                           │  Dashboard  │
                           └─────────────┘

† = planned
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Scraping | [n8n](https://n8n.io/) (self-hosted) |
| Backend | Kotlin, Spring Boot 3 |
| Telegram | [telegram-bot](https://github.com/DEHuckaKpyT/telegram-bot) (Kotlin DSL) |
| Frontend | React, Vite |
| Database | PostgreSQL |
| Deploy | Kubernetes, ArgoCD, Helm |

## Project Structure

This is a monorepo that coordinates individual service repositories via Git submodules:

| Submodule | Repository | Description |
|-----------|------------|-------------|
| `n8n/` | [job-hunter-n8n](https://github.com/mshykhov/job-hunter-n8n) | Scraping workflows (DOU live, Djinni/LinkedIn/Google Jobs planned) |
| `api/` | [job-hunter-api](https://github.com/mshykhov/job-hunter-api) | Kotlin Spring Boot backend + Telegram bot |
| `ui/` | job-hunter-ui | React web dashboard (coming soon) |

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
