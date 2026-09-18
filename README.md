# Job Hunter

Job Hunter is a modular system for collecting, matching, and tracking job
vacancies. A Kotlin scraper is replacing the legacy n8n ingestion path, the
Kotlin API owns durable workflow state and matching, and the React UI presents
the result.

## Components

- [job-hunter-api](https://github.com/mshykhov/job-hunter-api) - Kotlin/Spring Boot API, PostgreSQL persistence, scraper schedules, fenced leases, checkpoints, idempotent ingest, matching, and job state.
- [job-hunter-scraper](https://github.com/mshykhov/job-hunter-scraper) - stateless Kotlin source adapters and execution runtime. LinkedIn extraction uses a narrow JobSpy sidecar. Its root submodule registration is part of the migration delivery.
- [job-hunter-ui](https://github.com/mshykhov/job-hunter-ui) - React dashboard.
- [job-hunter-n8n](https://github.com/mshykhov/job-hunter-n8n) - temporary legacy ingestion for sources that have not completed production cutover.
- [job-hunter-automation](https://github.com/mshykhov/job-hunter-automation) - a separately configured, bounded runner for health checks and synthetic recovery workflows.

The root repository coordinates these components with Git submodules. It does not start a complete local stack by itself.

## Get the code

```sh
git clone --recurse-submodules https://github.com/mshykhov/job-hunter.git
cd job-hunter
git submodule update --init --recursive
```

Follow the README in each component for its local setup. The automation component needs a separately configured API and credentials; it does not browse vacancies or submit applications.

## Start here

1. For a UI preview without credentials or services, follow `npm run dev:mock` in [the UI](https://github.com/mshykhov/job-hunter-ui#run-locally).
2. For a local API and UI, start PostgreSQL and the API using the [API guide](https://github.com/mshykhov/job-hunter-api#run-locally), then start the UI against port 8095.
3. During migration, use [n8n](https://github.com/mshykhov/job-hunter-n8n#run-locally) for sources that have not cut over. Configure its API URL and credentials before activation, and keep one ingestion owner per source.

The Kotlin scraper and its API control plane ship disabled by default. Production
cutover is complete only after each source passes live acceptance, GitOps enables
that source in the scraper, and the corresponding n8n schedule is stopped.

See [service boundaries](docs/architecture/service-boundaries.md) and the [documentation map](docs/README.md) for the architecture.

## License

[MIT](LICENSE)
