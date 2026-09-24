# Job Hunter

Job Hunter is a modular system for collecting, matching, and tracking job
vacancies. A Kotlin scraper collects vacancies from eight sources, the
Kotlin API owns durable workflow state and matching, and the React UI presents
the result.

## Components

- [job-hunter-api](https://github.com/mshykhov-space/job-hunter-api) - Kotlin/Spring Boot API, PostgreSQL persistence, scraper schedules, fenced leases, checkpoints, idempotent ingest, matching, and job state.
- [job-hunter-scraper](https://github.com/mshykhov-space/job-hunter-scraper) - stateless Kotlin source adapters and execution runtime. LinkedIn extraction uses a narrow JobSpy sidecar.
- [job-hunter-ui](https://github.com/mshykhov-space/job-hunter-ui) - React dashboard.
- [job-hunter-automation](https://github.com/mshykhov-space/job-hunter-automation) - a separately configured, bounded runner for health checks and synthetic recovery workflows.

The root repository coordinates these components with Git submodules. It does not start a complete local stack by itself.

## Get the code

```sh
git clone --recurse-submodules https://github.com/mshykhov-space/job-hunter.git
cd job-hunter
git submodule update --init --recursive
```

Follow the README in each component for its local setup. The automation component needs a separately configured API and credentials; it does not browse vacancies or submit applications.

## Start here

1. For a UI preview without credentials or services, follow `npm run dev:mock` in [the UI](https://github.com/mshykhov-space/job-hunter-ui#run-locally).
2. For a local API and UI, start PostgreSQL and the API using the [API guide](https://github.com/mshykhov-space/job-hunter-api#run-locally), then start the UI against port 8095.
3. Start [the scraper](https://github.com/mshykhov-space/job-hunter-scraper#run-locally) with its API URL and machine credentials. Enable the desired sources in the API and scraper configuration.

The scraper ships disabled by default. Production runs all eight sources through
GitOps configuration. Each new run collects the last hour, with source-specific
date precision documented in the scraper. Sources run independently; PostgreSQL
leases prevent overlapping runs of the same source. The next scheduled run is due
15 minutes after completion. Legacy n8n workflows are archived.

See [service boundaries](docs/architecture/service-boundaries.md) and the [documentation map](docs/README.md) for the architecture.

## License

[MIT](LICENSE)
