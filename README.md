# Job Hunter

Job Hunter is a modular system for collecting, matching, and tracking job vacancies. The n8n workflows normalize source data, the Kotlin API owns persistence and matching, and the React UI presents the result.

## Components

- [job-hunter-api](https://github.com/mshykhov/job-hunter-api) - Kotlin/Spring Boot API, PostgreSQL persistence, matching, and job state.
- [job-hunter-ui](https://github.com/mshykhov/job-hunter-ui) - React dashboard.
- [job-hunter-n8n](https://github.com/mshykhov/job-hunter-n8n) - versioned n8n workflow exports.
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
3. Add [n8n](https://github.com/mshykhov/job-hunter-n8n#run-locally) when you want to ingest real sources. Configure its API URL and credentials before activating workflows.

See [service boundaries](docs/architecture/service-boundaries.md) and the [documentation map](docs/README.md) for the architecture.

## License

[MIT](LICENSE)
