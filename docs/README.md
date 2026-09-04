# Job Hunter documentation

Repository-level documentation describes contracts that span component
repositories. Implementation details, configuration, and runbooks remain next to
the service that owns them.

## Canonical documents

- [Service boundaries](architecture/service-boundaries.md) defines ownership,
  dependencies, durable state, restart behavior, and security boundaries.
- [Automation roadmap](backlog/automation-roadmap.md) is the ordered delivery
  backlog for private browser and application automation.

Historical specifications and completed implementation plans under
[`superpowers/specs/`](superpowers/specs/) and
[`superpowers/plans/`](superpowers/plans/) are snapshots. Files under `ideas/`
are working drafts until promoted into a canonical document or ADR.

Working notes are not architecture decisions. Promote a decision into an ADR or
one of the canonical documents before implementation depends on it.
