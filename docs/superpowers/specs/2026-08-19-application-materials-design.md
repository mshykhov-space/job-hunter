# Application Materials Design

**Status:** Owner-approved design, pending written-spec review
**Date:** 2026-08-19

## Intent

Extend Job Hunter with a versioned application-materials pipeline that prepares a
truthful, vacancy-specific CV, cover letter, and recruiter message for both manual
use and unattended application submission.

The feature must produce writing that sounds like the owner, improve machine
parsing and supported keyword coverage, preserve the exact material revision used
for every submission, and never invent experience. It runs through Codex with the
owner's ChatGPT-managed authentication on trusted private infrastructure. It does
not require an OpenAI API key for the primary path.

This design supersedes the existing application-workflow decision that cover
letters are always prohibited. A cover letter may be submitted only when it belongs
to a validated `READY_AUTOMATIC` application package.

## Decisions

- Use a separate Application Materials Compiler instead of extending the existing
  prompt-only outreach generator.
- Keep the canonical CV unchanged. Generate isolated derived CV inputs and
  artifacts for each vacancy.
- Let AI create new wording only from versioned, approved candidate facts with
  fragment-level provenance.
- Preserve companies, roles, dates, domains, section structure, and public aliases.
- Do not include age, date of birth, education, or a languages section in the CV.
- Store English proficiency as C1 for matching and required application fields,
  but do not add it to the CV unless the owner changes this policy.
- Generate normal packages with GPT-5.6 Terra. Use GPT-5.6 Sol only for one bounded
  repair attempt on difficult required material or for an explicit manual
  `Improve with Sol` action.
- Validate packages with deterministic code. Do not spend a second model call on
  routine validation.
- Allow unattended use without per-package approval only after all hard gates pass.
- Fall back to the validated base CV when a tailored CV fails. Omit an invalid
  optional cover letter. Pause only the affected application when a required cover
  letter remains invalid.
- Remove the old outreach path and obsolete CV generators after cutover. Do not
  keep two production generation paths.

## Scope

### In scope

- A versioned candidate profile and fact catalog compiled from the private CV
  repository.
- A versioned writing-style profile based on genuine owner-written examples.
- Immutable vacancy snapshots and application-package revisions.
- Tailored CV source, DOCX, PDF, cover letter, recruiter message, match gaps,
  provenance, and validation results.
- Manual package generation, preview, download, copy, revision history, and
  owner-edited child revisions.
- Automatic package preparation before browser work begins.
- Exact material references and digests in the submission manifest.
- Migration of existing saved outreach text and complete removal of the legacy
  generator, settings, endpoints, columns, UI, scripts, and contradictory docs.
- Deterministic factual, privacy, layout, parsing, and ATS-oriented checks.
- Regression evals for model, skill, fact-catalog, and renderer changes.

### Out of scope

- Inventing or inferring missing experience.
- Keyword stuffing, hidden text, universal "ATS score" claims, or attempts to
  bypass AI detectors.
- Company research outside the vacancy for the first release.
- Generating arbitrary screening answers under the cover-letter policy.
- Training or fine-tuning a model.
- Storing model chain-of-thought.
- Putting personal CV content or generated application artifacts in the public
  Job Hunter Git repositories.
- Holding a browser lease while generating or rendering materials.

## Architecture

```text
Private CV repository
  -> Profile Snapshot Compiler
  -> CandidateProfileVersion + FactCatalogVersion
                                      |
WritingStyleVersion ------------------+
JobDescriptionVersion ----------------+
                                      v
Job Hunter API/Postgres
  -> MaterialGenerationRequest
  -> trusted private materials launcher
      -> isolated read-only input workspace
      -> codex exec / GPT-5.6 Terra
      -> structured package JSON
      -> deterministic validators
      -> isolated DOCX/PDF renderer
      -> protected artifact upload
                                      |
                                      v
                       ApplicationPackageRevision
                         READY_AUTOMATIC or BLOCKED
                                      |
                    manual use -------+------- browser submission
```

Job Hunter remains the source of workflow state, versions, audit, and application
policy. The private CV repository remains the source of candidate facts, locked
profile structure, and document layout. The materials launcher is a bounded worker,
not a second backend or workflow database.

The worker is separate from Browser Runner. It has no browser profile, submit
capability, or authority to alter application state beyond its leased generation
request. It uses a dedicated minimal Codex profile and an isolated workspace. Job
descriptions are always treated as untrusted data.

Before claiming generation work, the launcher performs a read-only preflight for
the configured Terra and Sol model identifiers, ChatGPT-managed authentication,
required MCP initialization, structured-output support, renderer fingerprint, and
artifact-store access. A missing configured model fails with `MODEL_UNAVAILABLE`.
The launcher never silently substitutes another model.

## Component responsibilities

### Profile Snapshot Compiler

The compiler runs against a pinned commit of the private CV repository and emits:

- locked identity and CV-structure fields;
- normalized, public-safe candidate facts;
- source-span provenance;
- claim-strength limits;
- an explicit source allowlist and exclusion report;
- the base CV input and its validated artifact digests;
- a schema version and source commit.

It must not scan every file under `jobs/` indiscriminately. That directory currently
contains candidate experience, interview material, recruiter notes, and at least
one target vacancy. Only explicitly classified experience sources may contribute
candidate facts.

### Job Hunter API

The API owns generation requests, leases, input-version selection, package and
revision state, validation results, artifact metadata, manual edits, idempotency,
retention, and application linkage. It exposes manual UI endpoints and narrow
machine endpoints for the launcher. It does not call a model synchronously from a
job-detail HTTP request.

### Materials launcher

The launcher claims one generation request, builds a bounded workspace from pinned
resources, runs `codex exec --ephemeral` with structured output, invokes validators
and the renderer, uploads artifacts, and reports a typed outcome. Codex uses
ChatGPT-managed file-backed authentication on one trusted serialized runner stream.

### Renderer

The renderer consumes a derived CV YAML file and creates DOCX, PDF, and page
previews in a unique per-attempt directory. It reuses the current CV structure and
layout without mutating canonical `build/cv.yaml`.

The production renderer must pin Python dependencies, fonts, LibreOffice, and
other layout-relevant tools. Its fingerprint is part of the generation input and
validation result.

### Browser Runner

Browser Runner receives only a selected `READY_AUTOMATIC` revision. It uploads the
exact approved CV artifact and inserts the exact approved cover letter. It neither
generates nor rewrites material during the browser session.

## Candidate fact model

Each usable fact has a stable identifier and explicit public wording limits:

```yaml
id: nda-platform.spring6-migration
role_id: nda-platform
statement: Contributed to a Spring 6 migration across 15+ modules
max_claim_strength: CONTRIBUTED
skills:
  - Java
  - Spring Framework
  - Spring Security
metrics:
  modules: "15+"
public_company: Under NDA
classification: PUBLIC_SAFE
source:
  repository_commit: 0123456789abcdef
  path: jobs/pax8-platform-engineering.txt
  span_hash: sha256:...
```

Required fact properties:

- stable `fact_id` and owning role;
- canonical public-safe statement;
- maximum claim strength;
- supported skills, technologies, metrics, and domains;
- public alias and NDA classification;
- exact source reference and content hash;
- catalog schema and version.

Claim strengths form an ordered policy. A source recorded as `CONTRIBUTED` cannot
be rendered as `LED`, `OWNED`, or `ARCHITECTED`. The exact order is versioned in the
catalog schema and enforced in code.

Locked profile fields include name, contacts, company blocks and order, public
company aliases, roles, dates, domains, section order, age omission, education
omission, and language-section omission.

Allowed tailoring includes:

- selecting and ordering supported summary bullets;
- selecting and ordering verified skills;
- selecting, ordering, and carefully rewording experience bullets;
- using the vacancy's exact terminology when it maps to verified facts;
- reordering technologies in the title without changing the professional role.

Forbidden tailoring includes:

- adding, removing, or renaming company blocks outside the public-alias policy;
- changing dates, roles, or domains;
- introducing unsupported skills, metrics, projects, or outcomes;
- increasing claim strength;
- exposing protected employer names or internal details;
- adding age, date of birth, education, or a language section.

## Writing style

`WritingStyleVersion` contains explicit rules and genuine owner-written examples.
Generated material is never automatically fed back into the style profile.
Owner-edited text may be added only through a separate deliberate action.

Initial voice policy:

- professional English at C1 capability while retaining the owner's direct,
  technical voice;
- plain wording, short sentences, and concrete evidence;
- no generic self-praise or fabricated enthusiasm;
- no unsupported claims about company mission, product, or culture;
- no greeting or sign-off unless a target form specifically requires one;
- no age or education references;
- no em dash.

Default cover-letter policy:

- preferred length: 40-60 words;
- allowed normal range: 30-70 words;
- two or three sentences;
- at most 90 words only when the vacancy explicitly asks for detailed motivation;
- one relevant experience connection and one supported result;
- no restatement of the full CV.

Default recruiter-message policy:

- 25-45 words;
- conversational and specific;
- one role reference, one relevant fact, and a simple next step;
- failure never blocks application submission.

## Model routing and structured output

The default generation path makes one GPT-5.6 Terra call. The request includes the
pinned vacancy snapshot, selected profile/fact/style/policy versions, a compact set
of candidate facts, the output schema, and unambiguous authorization boundaries.

The response is strict structured data containing:

- normalized must-have and preferred requirements;
- selected fact IDs and uncovered gaps;
- tailored CV sections and fragment-level fact references;
- cover letter and sentence-level fact references;
- recruiter message and sentence-level fact references;
- warnings and an explicit statement of unsupported vacancy requirements.

Generated text uses a closed-world claim envelope. Every CV bullet and each factual
letter or message clause is split into factual fragments and non-factual connective
text. A factual fragment must reference its complete fact set and separately list
its claim verb, technologies, metrics, role, company alias, and domain terms. The
validator rejects any factual entity, metric, technology, or claim-strength token
that is absent from the referenced facts. Connective text cannot introduce named
entities, experience, metrics, or qualifications.

This constraint is what makes deterministic validation meaningful. Provenance
returned by the model is evidence to verify, not evidence to trust by itself.

The model does not decide whether its result is valid. Deterministic validators do.

GPT-5.6 Sol is permitted only when:

- a required material failed for a repairable content reason;
- the policy permits one bounded repair attempt;
- the repair receives typed validator failures and the same pinned facts; or
- the owner explicitly requests `Improve with Sol` in the manual UI.

Sol is not used to validate Terra output. There is at most one model repair attempt
per generation request. Repeated model loops are prohibited.

## Generation lifecycle

1. Freeze a `JobDescriptionVersion` from the exact vacancy content.
2. Select immutable profile, fact-catalog, writing-style, generation-policy, skill,
   schema, and renderer versions.
3. Compute the generation input hash and create or reuse a request.
4. Claim the request without acquiring a browser lease.
5. Materialize a bounded, isolated workspace.
6. Run Terra and parse the structured response.
7. Run deterministic validation.
8. If a required content failure is repairable and policy permits it, make one Sol
   repair attempt and validate again.
9. Create derived CV YAML without changing canonical CV data.
10. Render DOCX, PDF, and previews in a unique directory.
11. Validate the rendered documents and upload content-addressed artifacts.
12. Publish one immutable package revision atomically as `READY_AUTOMATIC`, or
    record a typed blocked outcome.
13. Manual UI may download, copy, or create a child revision.
14. Automation may claim browser work only with an eligible package revision.
15. The submission manifest records the exact revision and artifact digests used.

## Data model

### CandidateProfileVersion

An immutable candidate-profile snapshot with locked fields, public aliases, base CV
reference, private-source commit, schema version, and activation time.

### FactCatalogVersion

An immutable set of approved facts and provenance spans. A profile version selects
exactly one fact-catalog version.

### WritingStyleVersion

Immutable voice rules, approved owner-written example references, exclusions, and
activation time.

### JobDescriptionVersion

An immutable raw and normalized vacancy snapshot, discovery and target references,
content hash, capture time, and parser version.

### ApplicationPackage

The stable package identity for one application. It points to its current selected
revision without making that revision mutable.

### ApplicationPackageRevision

An immutable atomic package containing artifact references, generation origin,
input hash, parent revision, validation state, selected model route, created time,
and eligibility state.

Origins include `GENERATED_TERRA`, `GENERATED_SOL_REPAIR`, `USER_EDITED`,
`BASE_FALLBACK`, and `LEGACY_IMPORTED`.

### MaterialArtifact

A protected content-addressed artifact with type, SHA-256, media type, byte size,
storage reference, renderer fingerprint, extraction hash, and retention state.

Artifact types include `CV_SOURCE`, `CV_DOCX`, `CV_PDF`, `COVER_LETTER_TEXT`,
`RECRUITER_MESSAGE_TEXT`, `VALIDATION_REPORT`, and bounded page previews.

### MaterialClaimUsage

Maps a material fragment to one or more fact IDs, source versions, claim strength,
and validator outcome.

### MaterialGenerationAttempt

Records request, lease, model and CLI identifiers, skill/schema versions, input
hash, start/end times, repair relationship, token/usage metadata available from the
runtime, and typed outcome. It does not store chain-of-thought.

### MaterialValidationResult

Stores validator version, renderer fingerprint, hard and soft findings, reason
codes, counts, and final eligibility decision.

## State and idempotency

Package state is explicit:

```text
REQUESTED -> GENERATING -> VALIDATING -> RENDERING -> READY_AUTOMATIC
     |            |             |            |
     +------------+-------------+------------+-> BLOCKED

READY_AUTOMATIC -> SELECTED -> USED
                         \-> SUPERSEDED
```

An application can keep older `USED`, `SUPERSEDED`, `BLOCKED`, and manually edited
revisions. No state transition mutates material content.

The generation input hash includes:

- application key and job-description version;
- candidate profile and fact-catalog versions;
- writing-style and generation-policy versions;
- generation skill and structured-output schema versions;
- renderer fingerprint;
- locale and requested material types.

The same input hash returns the completed revision or the active request. Explicit
regeneration adds a request nonce and creates a new revision. Artifact content is
deduplicated by SHA-256. Editing one material creates a child revision that can
reuse unchanged artifact references.

## Hard validation gates

A revision becomes `READY_AUTOMATIC` only when all applicable checks pass:

- structured output matches the pinned schema;
- every referenced fact exists in the pinned catalog;
- every technology and metric is supported by referenced facts;
- wording does not exceed the maximum claim strength;
- locked fields and company-block order match the profile snapshot;
- no protected employer name, private detail, banned wording, age, education, or
  language section is present;
- no instructions from the vacancy appear as executable policy;
- cover-letter and recruiter-message lengths follow policy;
- CV contains no hidden text, keyword dump, or suspicious repetition;
- confirmed must-have terminology is used only when supported;
- DOCX and PDF are both extractable and preserve required headings and contacts;
- extracted key content is consistent between source, DOCX, and PDF;
- PDF has at most two pages;
- no experience block is split across pages;
- metadata author and document title follow profile policy;
- renderer and validator fingerprints are approved;
- required artifacts exist and their stored digests match.

Soft findings, such as an uncovered vacancy requirement, are visible as gaps and do
not become fabricated facts. They may lower a package-quality score but cannot
override a hard gate.

## ATS-oriented behavior

The feature does not claim a universal ATS score. It optimizes measurable behavior:

- successful text extraction from DOCX and PDF;
- standard headings and chronological experience;
- supported coverage of vacancy must-have terminology;
- absence of unsupported keywords and excessive repetition;
- consistent extracted text across formats;
- simple layout without hidden content or fragile visual structures.

The base CV remains the safe fallback. Tailoring changes relevance and ordering,
not the candidate's career history.

## Manual experience

The job detail page exposes an `Application Package` section with:

- `Queued`, `Generating`, `Ready`, `Blocked`, and `Used` status;
- tailored CV preview and PDF/DOCX download;
- cover letter and recruiter message with copy actions;
- requirements, supported coverage, and explicit gaps;
- a diff against the base CV;
- provenance for changed material fragments;
- validation findings and fallback use;
- complete revision history;
- the exact revision used for submission;
- `Generate package`, `Regenerate`, and bounded `Improve with Sol` actions.

Generation is asynchronous. The UI creates a request and observes its status. It
does not keep an HTTP request open while Codex and LibreOffice run.

Manual edits create immutable `USER_EDITED` child revisions and run the same hard
validators. A manually edited revision is not automatically eligible merely because
the owner created it.

## Automatic experience

Packages are generated only when the owner requests one manually or an application
becomes eligible for unattended submission. Job Hunter does not generate materials
for every discovered vacancy.

Automatic preparation finishes before browser work. `claim_work` returns the
selected package revision and exact artifact references. `prepare_submit` verifies
the package revision, artifact digests, input versions, application state, and
manifest before issuing a submit fence.

If a vacancy, profile, fact catalog, style, policy, skill, schema, or renderer changes,
the old revision remains auditable but cannot silently satisfy a new input hash.

## Fallback and error policy

### Per-application failures

- `JOB_DESCRIPTION_INSUFFICIENT`
- `UNSUPPORTED_CLAIM`
- `LOCKED_FIELD_CHANGED`
- `NDA_POLICY_VIOLATION`
- `STYLE_POLICY_VIOLATION`
- `ATS_PARSE_FAILED`
- `PAGE_LIMIT_EXCEEDED`
- `RENDER_FAILED`
- `REQUIRED_MATERIAL_INVALID`

These block or degrade only the affected application. The queue continues.

Fallback behavior:

- invalid tailored CV: select the validated base CV when policy permits;
- invalid optional cover letter: omit it;
- invalid required cover letter after the bounded repair: pause the application;
- invalid recruiter message: omit it without blocking submission;
- unavailable optional Sol fallback: apply the same deterministic fallback rather
  than retrying indefinitely.

### Global failures

- `CODEX_AUTH_REQUIRED`
- `MODEL_UNAVAILABLE`
- `PROFILE_SNAPSHOT_INVALID`
- `FACT_CATALOG_INVALID`
- `ARTIFACT_STORE_UNAVAILABLE`
- repeated provenance, locked-field, or NDA violations;
- an unapproved renderer fingerprint or failed renderer golden tests.

These pause the materials queue and raise one actionable operator alert. No browser
work is claimed for applications that require material generation.

## Security and privacy

- Job Hunter code remains safe for a public portfolio repository.
- Candidate sources and generated artifacts stay in private storage and trusted
  runtime paths.
- ChatGPT-managed `auth.json` is treated like a password, stored outside Git and
  artifacts, and used by only one serialized runner stream.
- The worker has least-privilege machine credentials scoped to generation work and
  artifact upload.
- Candidate snapshots, material text, validation details containing personal data,
  and binary artifacts are encrypted at rest with separately managed keys. Exact
  submitted materials are decrypted only through authorized application-audit and
  browser-upload paths.
- Vacancy content cannot change tools, policies, source allowlists, or output paths.
- Logs, traces, and metrics contain IDs, hashes, sizes, states, durations, and
  reason codes, not CV text, letters, contact data, or raw vacancy instructions.
- Exact submitted material remains available through protected application audit.
- Raw Codex event streams and failed temporary workspaces use short retention and
  are not ordinary application artifacts.

Package revisions used in submissions are retained with the application until
explicit deletion. Temporary inputs, raw runtime events, and failed render output
default to 7-30 day retention. No chain-of-thought is retained.

## Legacy cutover

The cutover is complete only when the old production path is gone.

1. Add the new package schema, worker contract, renderer, validators, and UI behind
   an inactive rollout policy.
2. Backfill non-empty existing `cover_letter` and `recruiter_message` values into
   `LEGACY_IMPORTED` revisions. Mark them unvalidated and never auto-send them.
3. Enable manual package generation and verify package history and artifacts.
4. Enable automatic preparation and browser consumption of exact ready revisions.
5. Switch the job UI completely to Application Packages.
6. Remove the old cover-letter and recruiter-message generation endpoints.
7. Remove `OutreachGenerator`, prompt-only generation, source-specific outreach
   prompts, outreach settings, tests, and UI.
8. Drop the old `user_jobs.cover_letter` and `user_jobs.recruiter_message` columns
   after backfill verification.
9. Delete unused private-CV generators `build_cv.py` and `build_roman_style.py`.
10. Delete the legacy Typst pipeline only after repository and automation reference
    scans prove it has no remaining consumer.
11. Update Job Hunter and CV READMEs, scoped CV rules, and the application-workflow
    design. Remove the rules that always skip required cover letters.
12. Verify no legacy endpoint, setting, column, script, workflow reference, test, or
    documentation instruction remains.

No compatibility shim or dual-write path remains after this sequence.

## Testing and evaluation

### Unit and contract tests

- profile and fact-catalog schema validation;
- source allowlists and classified-source exclusions;
- fact provenance and span hashes;
- claim-strength ordering;
- locked-field preservation;
- generation schema and typed outcomes;
- request idempotency and explicit regeneration;
- immutable parent/child revisions;
- artifact deduplication;
- manual-edit validation;
- package selection and exact manifest references;
- fallback decisions and bounded retry policy.

### Security and regression fixtures

- prompt injection embedded in vacancy content;
- a target vacancy accidentally placed among candidate sources;
- invented metric, technology, project, employer, or leadership claim;
- protected employer name in JSON, YAML, DOCX, or PDF;
- invalid or partial structured output;
- model timeout, auth failure, and unavailable Sol fallback;
- path traversal or output-path injection;
- stale lease, duplicate completion, and concurrent generation request;
- renderer crash and artifact-store partial failure.

### Document tests

- isolated per-attempt output directories;
- pinned dependency and renderer fingerprint;
- DOCX and PDF extraction;
- source/DOCX/PDF content consistency;
- page count and experience-block page mapping;
- required headings and contacts;
- metadata author and title;
- absence of hidden text and keyword dumps;
- golden render comparison for representative packages.

### Eval corpus

Maintain 30-50 representative real vacancies across Kotlin, Java, platform,
identity, B2B, stretch, and irrelevant roles. Store owner labels for relevant
facts, desired emphasis, and unsupported gaps. Keep 5-10 golden packages for
high-value regression checks.

Evaluate:

- factual support and provenance completeness;
- base CV versus tailored CV supported-keyword coverage;
- tone against genuine owner-written examples;
- pairwise material quality;
- output stability after model, skill, policy, fact-catalog, or renderer changes;
- latency and Codex usage by Terra and Sol route.

Hard release metrics:

- zero unsupported facts;
- zero locked-field changes;
- zero NDA leaks;
- 100% parse success for eligible DOCX and PDF artifacts;
- 100% provenance coverage for generated CV and letter claims;
- exact package revision and digest in every submission manifest.

Style quality and supported keyword coverage are quality metrics. They never permit
a package that fails a factual or privacy gate.

## Observability

Track generation request counts, route, latency, attempt outcome, validator reason
codes, fallback selection, renderer fingerprint, artifact sizes, ready-to-blocked
ratio, Sol fallback frequency, and exact package revision used by each application.

Do not put raw candidate facts, CV text, cover letters, recruiter messages, vacancy
text, contacts, or artifact paths in metrics or ordinary logs.

The operator UI is authoritative for package history and failures. Existing
Victoria/Grafana remains the technical diagnostics surface.

## Delivery sequence

1. **Profile compiler and isolated renderer**
   - classified fact sources and stable fact IDs;
   - pinned renderer and automated document validation;
   - validated base CV revision.
2. **Manual Application Package**
   - async queue and Terra structured generation;
   - package history, preview, download, copy, diff, gaps, and provenance;
   - deterministic gates and manual child revisions.
3. **Automatic preparation**
   - trusted launcher and ChatGPT-managed Codex authentication health;
   - queue leases, idempotency, fallback, alerts, and one bounded Sol repair.
4. **Browser integration**
   - exact CV upload and cover-letter insertion;
   - package version and digests in submit fencing and the immutable manifest.
5. **Quality loop and legacy removal**
   - representative eval corpus and model/skill upgrade gates;
   - migration of old data;
   - removal of all old outreach and CV-generation paths;
   - documentation synchronization and final legacy scans.

The sequence is a deployment safety boundary, not a per-application approval mode.
Once the automatic path is enabled, eligible packages require no manual review.

## Required changes to the application-workflow design

The existing application workflow must be updated during implementation to:

- replace the unconditional cover-letter prohibition with validated package policy;
- keep arbitrary screening free text separate and restricted;
- add material preparation before application readiness and browser claim;
- add profile, fact, style, vacancy, package, artifact, attempt, and validation
  versions to durable application memory;
- return the selected package revision from work claims;
- validate the revision and artifact digests in `prepare_submit`;
- include exact CV and cover-letter artifact references in the submission manifest;
- upload and insert prepared material without browser-time generation;
- convert the mandatory-cover-letter QualityMinds fixture into an end-to-end package
  fixture instead of an unconditional skip;
- add Application Package history, diff, provenance, gaps, validation, and downloads
  to the existing Job Hunter UI;
- preserve no-per-item-approval operation through hard factual and technical gates;
- keep material-generation machine endpoints separate from the eight application
  lifecycle MCP tools.

## Acceptance criteria

The feature is complete when:

- manual and automatic flows consume the same immutable package revisions;
- the canonical CV remains unchanged by vacancy-specific generation;
- every generated material claim is traceable to a pinned approved fact;
- no package can auto-submit after a hard validation failure;
- the validated base CV fallback works without a model retry;
- optional invalid text does not block an application;
- required invalid text pauses only the affected application;
- every submitted material has an exact immutable revision and digest;
- Codex generation uses Terra normally and Sol only through the bounded policy;
- generated materials and personal facts never enter public Git history;
- all specified legacy code, storage, UI, scripts, and contradictory documentation
  are removed after verified cutover;
- the hard release metrics pass on the representative eval corpus.
