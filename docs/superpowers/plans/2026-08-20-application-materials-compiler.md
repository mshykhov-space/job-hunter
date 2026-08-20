# Application Materials Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy outreach generator with a private, versioned application-materials compiler that prepares a truthful ATS-oriented CV, a short human cover letter, and a recruiter message for manual use now, while exposing the same package contract to future browser automation.

**Architecture:** The private CV repository owns the public-safe fact catalog, approved wording variants, deterministic DOCX/PDF rendering, and base-CV fallback. The Kotlin API owns encrypted durable state, immutable revisions, leases, provenance, and owner/machine endpoints. The existing private TypeScript automation runner claims work, uses one GPT-5.6 Terra structured generation call, validates deterministically, optionally performs one GPT-5.6 Sol repair, invokes the private renderer CLI, and uploads an immutable package. The React UI requests, monitors, compares, downloads, and copies packages. Browser submission is intentionally not implemented in this slice; it will call the same `ensureReady` API and record the exact submitted revision once the application lifecycle exists.

**Tech Stack:** Python 3.10+, PyYAML, python-docx, LibreOffice, Poppler, pytest; Kotlin 2.1, Spring Boot 3.5, Spring Data JPA, Flyway, PostgreSQL, JDK AES-256-GCM, JUnit 5, MockK, Testcontainers; Node.js 24, TypeScript 5.9, Zod, Codex CLI, Vitest; React 19, Ant Design 6, TanStack Query, Vitest, Testing Library.

---

## Scope and fixed product decisions

- The canonical private source is `/Users/myron/cv`. Never derive candidate facts by scanning every file under `jobs/`; some files are target vacancies and some contain NDA-sensitive names.
- CV structure remains `Header -> Professional Summary -> Core Qualifications -> Experience`, maximum two pages. Company, role, dates, domain, contacts, and section order are locked.
- The compiler may select, order, and keyword-align only approved public-safe variants. It cannot invent employers, dates, technologies, metrics, responsibilities, or experience.
- `English C1` is stored only as a matching/form fact. Age, date of birth, education, and a languages section are not renderable and must not appear in CV, cover letter, or recruiter message.
- Cover letter target is 40-60 words, accepted range 30-70 words, two or three sentences. A vacancy may explicitly require up to 90 words. Recruiter message target is 25-45 words.
- Default route is one `gpt-5.6-terra` call. Validation is deterministic. `gpt-5.6-sol` is allowed for one bounded repair after a required artifact fails, or one explicit owner-triggered improvement. There is no AI review loop and no silent model substitution.
- If a tailored CV fails, publish the validated base CV for the package. Omit an invalid optional cover letter. Pause only that request when a required cover letter fails. An invalid recruiter message never blocks the package.
- Every regeneration creates a new immutable revision. A future application submission must store the submitted revision ID and artifact SHA-256 values.
- Legacy outreach strings are imported as `LEGACY_IMPORTED`, read-only, and never eligible for automatic use. After the replacement UI and migration verification pass, delete the old generator, endpoints, settings, fields, and unused CV build scripts.
- Artifact bodies and private profile/tone data are encrypted before PostgreSQL persistence. Plaintext exists only in process memory and over authenticated TLS. Logs contain IDs, hashes, statuses, durations, and validator codes, never content.
- Ready revisions are retained until explicit owner deletion; future submitted revisions will be deletion-fenced by the application audit record. Raw Codex events are never persisted, and failed/request temporary directories are wiped immediately after terminal handling.

## Delivery boundary

This plan delivers a complete manual workflow and the shared worker/API foundation:

1. Import a versioned private candidate profile.
2. Request a package from a vacancy in the UI.
3. Let the private runner generate, validate, render, and persist it unattended.
4. Inspect provenance, compare revisions, download CV PDF/DOCX, and copy short messages.
5. Trigger one explicit Sol improvement without overwriting history.

It does not automate website form submission. That integration starts only after the application lifecycle and browser adapter exist. The integration point delivered here is `ApplicationMaterialService.ensureReady(ownerId, jobId, requestedKinds, mode)`; a later submit worker must call it and persist `submittedRevisionId` plus hashes before touching a website.

## Phase 0: Isolate the work and lock contracts

### Task 1: Create clean worktrees from current upstream heads

**Files:**
- Read: `/Users/myron/IdeaProjects/job-hunter/docs/superpowers/specs/2026-08-19-application-materials-design.md`
- Read: `/Users/myron/IdeaProjects/job-hunter/api/AGENTS.md`
- Read: `/Users/myron/IdeaProjects/job-hunter/ui/AGENTS.md`
- Read: `/Users/myron/IdeaProjects/job-hunter-automation/AGENTS.md`
- Read: `/Users/myron/cv/AGENTS.md`

- [ ] **Step 1: Verify all four repositories and preserve the dirty coordinator checkout**

Run:

```bash
git -C /Users/myron/IdeaProjects/job-hunter status --short --branch
git -C /Users/myron/IdeaProjects/job-hunter/api status --short --branch
git -C /Users/myron/IdeaProjects/job-hunter/ui status --short --branch
git -C /Users/myron/IdeaProjects/job-hunter-automation status --short --branch
git -C /Users/myron/cv status --short --branch
```

Expected: record existing user changes; do not clean, reset, checkout, or stage them.

- [ ] **Step 2: Fetch and create isolated feature worktrees**

Run:

```bash
git -C /Users/myron/IdeaProjects/job-hunter/api fetch origin
git -C /Users/myron/IdeaProjects/job-hunter/api worktree add /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api -b feat/application-materials origin/master
git -C /Users/myron/IdeaProjects/job-hunter/ui fetch origin
git -C /Users/myron/IdeaProjects/job-hunter/ui worktree add /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui -b feat/application-materials origin/master
git -C /Users/myron/IdeaProjects/job-hunter-automation fetch origin
git -C /Users/myron/IdeaProjects/job-hunter-automation worktree add /Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials -b feat/application-materials origin/master
git -C /Users/myron/cv fetch origin
git -C /Users/myron/cv worktree add /Users/myron/.worktrees/cv-application-materials -b feat/application-materials origin/master
```

Expected: four clean worktrees, each based on current `origin/master`. If a branch exists, inspect it and resume it instead of creating another branch.

- [ ] **Step 3: Run baselines in every worktree**

Run:

```bash
cd /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api && ./gradlew test
cd /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui && npm ci && npm test
cd /Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials && npm ci && npm run verify
cd /Users/myron/.worktrees/cv-application-materials && ./build/build.sh
```

Expected: all existing tests pass and the current base CV renders to no more than two pages. Record any pre-existing failure before feature work.

### Task 2: Define the versioned cross-repository JSON contracts

**Files:**
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/contracts/application-materials/v1/candidate-profile.schema.json`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/contracts/application-materials/v1/fact-catalog.schema.json`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/contracts/application-materials/v1/writing-style.schema.json`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/contracts/application-materials/v1/generation-input.schema.json`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/contracts/application-materials/v1/generation-output.schema.json`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/contracts/application-materials/v1/render-request.schema.json`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/contracts/application-materials/v1/examples/synthetic-profile.json`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/contracts.ts`
- Test: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/__tests__/contracts.test.ts`

- [ ] **Step 1: Write failing schema-contract tests**

Test that the synthetic profile accepts:

```ts
export const MATERIALS_SCHEMA_VERSION = "application-materials/v1" as const;

export const selectedVariantSchema = z.object({
  factId: z.string().min(1),
  variantId: z.string().min(1),
});

export const generationOutputSchema = z.object({
  schemaVersion: z.literal(MATERIALS_SCHEMA_VERSION),
  summaryVariantIds: z.array(z.string()).min(2).max(5),
  qualificationIds: z.array(z.string()).min(4),
  experience: z.array(z.object({
    experienceId: z.string(),
    selectedVariants: z.array(selectedVariantSchema),
  })),
  coverLetter: z.object({
    text: z.string(),
    sourceFactIds: z.array(z.string()),
    requiredByVacancy: z.boolean(),
  }).nullable(),
  recruiterMessage: z.object({
    text: z.string(),
    sourceFactIds: z.array(z.string()),
  }).nullable(),
});
```

Run: `npm test -- src/materials/__tests__/contracts.test.ts`

Expected: FAIL because schemas and fixtures do not exist.

- [ ] **Step 2: Implement schemas with closed-world profile fields**

The candidate schema must require:

- `schemaVersion`. The bundle manifest, not the profile document, adds `profileVersion` as the SHA-256 of the final canonical `candidate-profile.json`; this avoids a self-referential hash.
- Locked `identity`, `contacts`, `experience[].title`, `experience[].years`, `experience[].company`, and `experience[].domain`, plus the referenced fact-catalog hash.
- A separate fact catalog with `summaryVariants`, `qualificationItems`, and experience facts using explicit `factId` and `variants[].variantId/text`.
- Per-fact allowlists for technologies, metrics, proper nouns, and claim anchors.
- A separate writing-style document with immutable voice rules and tagged owner-approved examples, never candidate claims.
- `privateMatchingFacts.englishLevel = "C1"` marked `renderable: false`.
- `forbiddenRenderFields = ["age", "dateOfBirth", "education", "languages"]`.
- `baseArtifacts` hashes for DOCX and PDF.
- No real candidate data in the public automation repository; use synthetic `Alex Example` fixtures.

- [ ] **Step 3: Make contract tests pass**

Run: `npm test -- src/materials/__tests__/contracts.test.ts`

Expected: PASS for the synthetic fixture and FAIL for fixtures containing an unknown variant, a renderable C1 field, or an education section.

- [ ] **Step 4: Commit the public contract**

Run:

```bash
git add contracts/application-materials src/materials/contracts.ts src/materials/__tests__/contracts.test.ts
git commit -m "feat(materials): define versioned package contracts"
```

## Phase 1: Build the private candidate compiler and renderer

### Task 3: Replace mixed `jobs/*` discovery with an explicit public-safe fact catalog

**Files:**
- Create: `/Users/myron/.worktrees/cv-application-materials/profile/profile.yaml`
- Create: `/Users/myron/.worktrees/cv-application-materials/profile/tone-examples.yaml`
- Create: `/Users/myron/.worktrees/cv-application-materials/profile/schema/candidate-profile.schema.json`
- Create: `/Users/myron/.worktrees/cv-application-materials/profile/schema/fact-catalog.schema.json`
- Create: `/Users/myron/.worktrees/cv-application-materials/profile/schema/writing-style.schema.json`
- Create: `/Users/myron/.worktrees/cv-application-materials/src/cv_materials/models.py`
- Create: `/Users/myron/.worktrees/cv-application-materials/src/cv_materials/profile_loader.py`
- Create: `/Users/myron/.worktrees/cv-application-materials/tests/test_profile_loader.py`
- Modify: `/Users/myron/.worktrees/cv-application-materials/build/cv.yaml`
- Modify: `/Users/myron/.worktrees/cv-application-materials/.gitignore`

- [ ] **Step 1: Write failing allowlist and policy tests**

Cover six named cases: `test_loader_never_scans_jobs_directory`, `test_every_renderable_fact_has_approved_variant`, `test_locked_identity_matches_base_cv`, `test_c1_is_private_and_not_renderable`, `test_age_education_and_languages_are_forbidden`, and `test_public_catalog_contains_no_protected_nda_names`.

Run: `python3 -m pytest tests/test_profile_loader.py -q`

Expected: FAIL because the profile package does not exist.

- [ ] **Step 2: Create the typed catalog**

Use stable IDs such as `exp-marketplace-platform`, `fact-spring6-migration`, and `spring6-migration-short`. Store the current CV sentence as an approved `base` variant and add only owner-approved alternatives. Do not copy protected names from raw experience notes. Each fact records:

```yaml
id: fact-spring6-migration
claimAnchors: [migrated, Spring 6, 15+ modules]
technologies: [Java, Spring Framework, Spring Security, Spring Data]
metrics: [15+]
variants:
  - id: spring6-migration-base
    text: Drove Spring 6 migration across 15+ modules, including Security and Data upgrades.
  - id: spring6-migration-ats
    text: Led a 15+ module migration to Spring 6, Spring Security 6, and Spring Data 3.
```

`profile.yaml` is the only source used by export and render commands. `build/cv.yaml` becomes a generated base projection checked into the private repository for easy visual editing and review.

- [ ] **Step 3: Add genuine tone examples**

Store 5-10 short owner-written or owner-approved examples, each tagged `cover_letter` or `recruiter_message`. Keep them factual, direct, C1 English, without formal filler such as “I am writing to express my interest”. Tone examples guide style but are never treated as candidate facts.

- [ ] **Step 4: Pass loader tests**

Run: `python3 -m pytest tests/test_profile_loader.py -q`

Expected: PASS; loading succeeds without reading `jobs/ciklum_java_kotlin.txt` or any other unlisted raw note.

- [ ] **Step 5: Commit the catalog**

Run:

```bash
git add profile build/cv.yaml .gitignore src/cv_materials tests/test_profile_loader.py
git commit -m "feat(profile): add public-safe candidate fact catalog"
```

### Task 4: Refactor rendering into a deterministic, isolated CLI

**Files:**
- Create: `/Users/myron/.worktrees/cv-application-materials/pyproject.toml`
- Create: `/Users/myron/.worktrees/cv-application-materials/src/cv_materials/render_docx.py`
- Create: `/Users/myron/.worktrees/cv-application-materials/src/cv_materials/render_pdf.py`
- Create: `/Users/myron/.worktrees/cv-application-materials/src/cv_materials/render_cli.py`
- Create: `/Users/myron/.worktrees/cv-application-materials/src/cv_materials/validation.py`
- Create: `/Users/myron/.worktrees/cv-application-materials/tests/test_render_cli.py`
- Create: `/Users/myron/.worktrees/cv-application-materials/tests/fixtures/render-request.json`
- Modify: `/Users/myron/.worktrees/cv-application-materials/build/build.sh`
- Modify: `/Users/myron/.worktrees/cv-application-materials/build/generate_docx.py`

- [ ] **Step 1: Write failing renderer tests**

Assert that:

- Two concurrent renders use separate temporary directories and cannot overwrite each other.
- The output manifest contains DOCX/PDF SHA-256 values and page count.
- The same request renders the same visible text and section order.
- Every experience block has Word keep-together settings.
- More than two PDF pages fails with `CV_PAGE_LIMIT_EXCEEDED`.
- Education/languages/age tokens fail with `FORBIDDEN_FIELD`.
- `soffice` and `pdftoppm` absence fails preflight before generation.

Run: `python3 -m pytest tests/test_render_cli.py -q`

Expected: FAIL against the fixed-name shell script.

- [ ] **Step 2: Extract the current layout without visual redesign**

Move the reusable functions from `build/generate_docx.py` into `src/cv_materials/render_docx.py`. Preserve font, margins, section order, hyperlinks, metadata, and keep-together behavior. `generate_docx.py` becomes a compatibility wrapper temporarily:

```python
from cv_materials.render_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Implement an isolated CLI**

Command:

```bash
python -m cv_materials.render_cli \
  --request tests/fixtures/render-request.json \
  --output-dir build/out/example
```

The CLI must sanitize the requested output directory, write source JSON before invoking LibreOffice, use a unique temporary LibreOffice profile, call subprocesses with argument arrays, and atomically rename completed artifacts. Output:

```json
{
  "schemaVersion": "application-materials/v1",
  "status": "VALID",
  "pageCount": 2,
  "artifacts": [
    {"kind": "CV_DOCX", "path": "cv.docx", "sha256": "0000000000000000000000000000000000000000000000000000000000000000"},
    {"kind": "CV_PDF", "path": "cv.pdf", "sha256": "0000000000000000000000000000000000000000000000000000000000000000"}
  ],
  "validatorCodes": []
}
```

- [ ] **Step 4: Pin the Python toolchain**

Use Python `>=3.10`, `PyYAML==6.0.3`, `python-docx==1.2.0`, a `dev` extra with `pytest==8.4.2`, and console script `cv-materials-render`. `build/build.sh` must use `set -euo pipefail`, quote variables, install the project rather than ad hoc packages, and write into `build/out/base`.

- [ ] **Step 5: Run renderer tests and visually verify the base PDF**

Run:

```bash
python3 -m pip install -e '.[dev]'
python3 -m pytest -q
./build/build.sh
pdfinfo build/out/base/cv.pdf | rg '^Pages:'
pdftoppm -png -r 110 build/out/base/cv.pdf build/out/base/page
```

Expected: tests pass; `Pages: 2` or fewer; both page images show no split experience block, clipping, or accidental new section.

- [ ] **Step 6: Commit the renderer**

Run:

```bash
git add pyproject.toml src/cv_materials tests build/build.sh build/generate_docx.py
git commit -m "refactor(render): isolate deterministic CV compiler"
```

### Task 5: Export an immutable profile bundle and base fallback

**Files:**
- Create: `/Users/myron/.worktrees/cv-application-materials/src/cv_materials/export_cli.py`
- Create: `/Users/myron/.worktrees/cv-application-materials/src/cv_materials/profile_projection.py`
- Create: `/Users/myron/.worktrees/cv-application-materials/tests/test_export_cli.py`
- Create: `/Users/myron/.worktrees/cv-application-materials/scripts/install-renderer-runtime.sh`
- Modify: `/Users/myron/.worktrees/cv-application-materials/README.md`
- Modify: `/Users/myron/.worktrees/cv-application-materials/build/README.md`

- [ ] **Step 1: Write failing export tests**

Test stable canonical JSON hashing, rejection of unknown source files, base-artifact hash inclusion, path-scoped dirty-source rejection, source-commit capture, no forbidden render fields, and no plaintext archive after a failed export.

- [ ] **Step 2: Implement export**

Command:

```bash
python -m cv_materials.export_cli --output-dir build/profile-bundle
```

Write:

```text
build/profile-bundle/
  candidate-profile.json
  fact-catalog.json
  writing-style.json
  base-cv.docx
  base-cv.pdf
  manifest.json
```

`profileVersion`, `factCatalogVersion`, and `writingStyleVersion` are the SHA-256 values of their canonical JSON documents. `manifest.json` includes schema version, all three version hashes, the current private-source commit, artifact hashes, renderer version, page count, and validation codes. Export refuses uncommitted changes under `profile/`, `src/cv_materials/`, and renderer-owned `build/` files, while unrelated private preparation notes do not block it. The bundle contains no raw notes.

- [ ] **Step 3: Add the LXD renderer installation script**

Install only the packaged private CLI and pinned runtime into `/opt/job-hunter-cv`, then expose `/opt/job-hunter-cv/bin/cv-materials-render`. Do not clone or mount the working CV repository into the long-running automation process. Verify the binary with a synthetic render request.

- [ ] **Step 4: Verify and commit**

Run:

```bash
python3 -m pytest -q
python -m cv_materials.export_cli --output-dir build/profile-bundle
python -m cv_materials.render_cli --request tests/fixtures/render-request.json --output-dir build/out/smoke
git add src/cv_materials tests scripts README.md build/README.md
git commit -m "feat(profile): export immutable candidate bundle"
```

## Phase 2: Add encrypted, immutable material state to the API

### Task 6: Add Flyway schema and domain state machine

**Files:**
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/resources/db/migration/V27__add_application_materials.sql`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/MaterialStatus.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/MaterialKind.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/MaterialOrigin.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/CoverLetterPolicy.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/MaterialStateMachine.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/CandidateProfileVersionEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/CandidateProfileVersionRepository.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/FactCatalogVersionEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/FactCatalogVersionRepository.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/WritingStyleVersionEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/WritingStyleVersionRepository.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/JobDescriptionVersionEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/JobDescriptionVersionRepository.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/ApplicationMaterialPackageEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/ApplicationMaterialPackageRepository.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/ApplicationMaterialRequestEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/ApplicationMaterialRequestRepository.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/ApplicationMaterialRevisionEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/ApplicationMaterialRevisionRepository.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/ApplicationMaterialArtifactEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/ApplicationMaterialArtifactRepository.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/ApplicationMaterialRevisionArtifactEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/ApplicationMaterialRevisionArtifactRepository.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/MaterialClaimUsageEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/MaterialClaimUsageRepository.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/MaterialGenerationAttemptEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/MaterialGenerationAttemptRepository.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/MaterialValidationResultEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/MaterialValidationResultRepository.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/LegacyOutreachImportEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/LegacyOutreachImportRepository.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/ApplicationDataMigrationEntity.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/ApplicationDataMigrationRepository.kt`
- Test: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/test/kotlin/com/mshykhov/jobhunter/application/materials/MaterialStateMachineTest.kt`
- Test: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/test/kotlin/com/mshykhov/jobhunter/application/materials/MaterialMigrationIntegrationTest.kt`

- [ ] **Step 1: Write failing transition tests**

Allowed transitions:

```text
QUEUED -> CLAIMED -> GENERATING -> VALIDATING -> RENDERING -> READY
CLAIMED|GENERATING|VALIDATING|RENDERING -> QUEUED        expired lease
GENERATING|VALIDATING|RENDERING -> READY_WITH_FALLBACK   valid base CV fallback
GENERATING|VALIDATING|RENDERING -> BLOCKED               required artifact failed
QUEUED|CLAIMED|GENERATING|VALIDATING|RENDERING -> FAILED terminal infrastructure failure
READY|READY_WITH_FALLBACK -> QUEUED                      explicit new revision request only
```

Terminal revisions are immutable; regeneration creates a new request/revision, not a state reset on an old revision.

- [ ] **Step 2: Create V27 schema**

Create tables:

- `fact_catalog_versions`: owner, schema version, content hash, encrypted approved facts/variants/provenance, created timestamp.
- `candidate_profile_versions`: owner, schema/profile version, content hash, encrypted locked identity/profile JSON, fact-catalog version ID, base DOCX/PDF artifact IDs, validation metadata, created timestamp, active flag.
- `writing_style_versions`: owner, content hash, encrypted voice rules and approved tone examples, created timestamp, active flag. Editing examples creates a new immutable version.
- `job_description_versions`: owner, job ID, content hash, encrypted raw/normalized vacancy snapshot, parser version, capture timestamp; unique `(owner_id, job_id, content_hash)`.
- `application_material_packages`: stable owner/job identity, selected revision ID, created/updated timestamps; unique `(owner_id, job_id)`.
- `application_material_requests`: package ID, job-description/profile/fact-catalog/writing-style version IDs, status, request mode, requested kinds, cover-letter policy, encrypted proposed owner edits when mode is `USER_EDIT_VALIDATION`, generation-policy/schema/renderer versions, model route, input hash, lease owner/token/expiry, attempt count, idempotency key, parent revision ID, created/updated timestamps.
- `application_material_revisions`: package/request IDs, monotonically increasing package revision, parent revision ID, origin, input hash, generator model, renderer version, eligibility state, manifest JSONB, created timestamp.
- `application_material_artifacts`: owner, kind, media type, encrypted bytes, plaintext SHA-256, extraction SHA-256, byte size, renderer fingerprint, retention state, created timestamp; unique `(owner_id, kind, plaintext_sha256)` for content deduplication.
- `application_material_revision_artifacts`: revision ID, artifact ID, kind; unique `(revision_id, kind)`.
- `material_claim_usages`: revision ID, artifact kind, JSON path, fact ID, variant ID, source version IDs, claim strength, validator outcome.
- `material_generation_attempts`: request/lease IDs, route/model, CLI/schema/skill/renderer versions, input hash, repair-of attempt ID, start/end timestamps, usage JSONB when available, typed outcome; never chain-of-thought or generated content.
- `material_validation_results`: revision or attempt ID, validator version, hard/soft findings JSONB, reason counts, eligibility decision, created timestamp.
- `legacy_outreach_imports`: owner/job, kind, encrypted text, origin fixed to `LEGACY_IMPORTED`, imported timestamp.

Add foreign keys, owner/job indexes, `status + lease_expires_at` claim index, and unique idempotency/input keys per owner. Use `bytea` for encrypted bodies; no plaintext content columns. Candidate base artifact foreign keys may be populated after the artifact rows are inserted in the same profile-import transaction.

- [ ] **Step 3: Pass migration and state tests**

Run:

```bash
./gradlew test --tests '*MaterialStateMachineTest' --tests '*MaterialMigrationIntegrationTest'
```

Expected: PASS against Testcontainers PostgreSQL, including rollback on duplicate artifact kind.

- [ ] **Step 4: Commit**

Run:

```bash
git add src/main/resources/db/migration/V27__add_application_materials.sql src/main/kotlin/com/mshykhov/jobhunter/application/materials src/test/kotlin/com/mshykhov/jobhunter/application/materials
git commit -m "feat(materials): add immutable package state"
```

### Task 7: Implement fail-closed encryption and artifact persistence

**Files:**
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/infrastructure/materials/MaterialEncryptionProperties.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/infrastructure/materials/MaterialEncryptionService.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/infrastructure/materials/EncryptedMaterialStore.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/test/kotlin/com/mshykhov/jobhunter/infrastructure/materials/MaterialEncryptionServiceTest.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/test/kotlin/com/mshykhov/jobhunter/infrastructure/materials/EncryptedMaterialStoreIntegrationTest.kt`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/resources/application.yml`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/test/resources/application-test.yml`

- [ ] **Step 1: Write failing crypto tests**

Verify random 96-bit nonce per encryption, AES-256-GCM authentication, additional authenticated data containing owner ID + record ID + kind, round trip for binary artifacts, different ciphertext for identical plaintext, and hard failure on wrong key/tampering. Unlike `AiEncryptionConverter`, decryption failure must never return an empty value.

- [ ] **Step 2: Implement the service using only JDK crypto**

Configuration:

```yaml
job-hunter:
  materials:
    encryption-key: ${MATERIAL_ENCRYPTION_KEY:}
    max-artifact-bytes: ${MATERIAL_MAX_ARTIFACT_BYTES:5242880}
```

Require a base64-encoded 32-byte key outside tests. Store an explicit envelope version with nonce and ciphertext so key rotation can be introduced without changing every table.

- [ ] **Step 3: Implement content-addressed persistence checks**

Calculate SHA-256 before encryption, enforce size/media-type allowlists, reject mismatched client hashes, and return bytes only after owner/runner authorization. Do not log payloads or exception byte arrays.

- [ ] **Step 4: Pass tests and commit**

Run:

```bash
./gradlew test --tests '*MaterialEncryptionServiceTest' --tests '*EncryptedMaterialStoreIntegrationTest'
git add src/main/kotlin/com/mshykhov/jobhunter/infrastructure/materials src/test/kotlin/com/mshykhov/jobhunter/infrastructure/materials src/main/resources/application.yml src/test/resources/application-test.yml
git commit -m "feat(materials): encrypt private package content"
```

### Task 8: Add profile import and owner-facing package APIs

**Files:**
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/CandidateProfileService.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/ApplicationMaterialService.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/materials/MaterialProfileController.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/materials/ApplicationMaterialController.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/materials/dto/CreateMaterialRequest.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/materials/dto/CandidateProfileSummaryResponse.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/materials/dto/ApplicationMaterialRequestResponse.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/materials/dto/ApplicationMaterialRevisionResponse.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/materials/dto/ApplicationMaterialArtifactResponse.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/materials/dto/MaterialValidationIssueResponse.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/materials/dto/SaveWritingStyleRequest.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/materials/dto/WritingStyleVersionResponse.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/materials/dto/CreateMaterialChildRevisionRequest.kt`
- Test: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/test/kotlin/com/mshykhov/jobhunter/api/rest/materials/MaterialProfileControllerIntegrationTest.kt`
- Test: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/test/kotlin/com/mshykhov/jobhunter/api/rest/materials/ApplicationMaterialControllerIntegrationTest.kt`

- [ ] **Step 1: Write failing owner API tests**

Cover:

```text
POST /api/materials/profiles                         multipart profile + fact catalog + writing style + base DOCX/PDF
GET  /api/materials/profiles                         version metadata only
POST /api/jobs/{jobId}/materials                     queue requested artifacts
GET  /api/jobs/{jobId}/materials                     status and immutable revision summaries
GET  /api/materials/revisions/{revisionId}/artifacts/{kind}
POST /api/materials/revisions/{revisionId}/improve-with-sol
POST /api/materials/revisions/{revisionId}/children  save validated owner text edits
POST /api/materials/revisions/{revisionId}/select    select an existing eligible revision
DELETE /api/materials/packages/{packageId}           explicit private-data deletion
```

Assert owner isolation, idempotent double-click behavior, exact HTTP media types/filenames, no content in list responses, a new revision request for Sol improvement, immutable parent artifacts after an owner edit, selection of eligible revisions only, and deletion of unreferenced artifact bodies only.

- [ ] **Step 2: Implement profile import validation**

Reject unsupported schema versions, hash mismatches, missing base artifacts, invalid base-CV validation status, renderable private facts, and forbidden fields. Activating a profile version deactivates the previous version but never deletes it.

- [ ] **Step 3: Implement package requests**

`ApplicationMaterialService.ensureReady(ownerId, jobId, requestedKinds, mode)` must:

1. Snapshot the complete vacancy text and metadata hash.
2. Resolve the active profile version.
3. Accept an explicit cover-letter policy from the owner or future form adapter: `OPTIONAL_STANDARD`, `REQUIRED_STANDARD`, or `REQUIRED_EXTENDED`. Only `REQUIRED_EXTENDED` permits 90 words; vacancy prose alone cannot silently escalate it.
4. Return an existing `READY` revision for the same job/profile/vacancy hash/requested kinds/policy unless regeneration is explicit.
5. Otherwise create `QUEUED` with a stable idempotency key.
6. Never invoke AI inside the API process.

- [ ] **Step 4: Add concise DTOs**

Expose status, requested kinds, revision IDs, artifact hashes/sizes, validation codes, generator model, origin, and timestamps. Expose provenance as fact/variant IDs. Never expose encrypted columns, lease tokens, or candidate profile JSON to owner list endpoints.

- [ ] **Step 5: Implement immutable owner edits and explicit deletion**

An owner may replace cover-letter or recruiter-message text. The API encrypts that proposed text into a `USER_EDIT_VALIDATION` request; the same private worker runs the normal deterministic validators without an AI call and stores a `USER_EDITED` child revision reusing unchanged CV artifacts only if eligible. It never mutates the parent. Selecting changes only `application_material_packages.selected_revision_id`. Explicit package deletion removes package/request/revision/link rows and garbage-collects artifact bodies only when no profile, revision, legacy import, or future submission reference remains.

- [ ] **Step 6: Pass owner tests and commit**

Run:

```bash
./gradlew test --tests '*MaterialProfileControllerIntegrationTest' --tests '*ApplicationMaterialControllerIntegrationTest'
git add src/main/kotlin/com/mshykhov/jobhunter/application/materials src/main/kotlin/com/mshykhov/jobhunter/api/rest/materials src/test/kotlin/com/mshykhov/jobhunter/api/rest/materials
git commit -m "feat(materials): expose owner package workflow"
```

### Task 9: Add machine lease, input, completion, and heartbeat integration

**Files:**
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/MaterialLeaseService.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/automation/AutomationMaterialController.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/automation/dto/AutomationMaterialClaimRequest.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/automation/dto/AutomationMaterialClaimResponse.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/automation/dto/AutomationMaterialHeartbeatRequest.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/automation/dto/AutomationMaterialCompletionMetadata.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/automation/dto/AutomationMaterialFailureRequest.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/test/kotlin/com/mshykhov/jobhunter/api/rest/automation/AutomationMaterialControllerIntegrationTest.kt`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/infrastructure/security/SecurityConfig.kt`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/infrastructure/metrics/AutomationMetrics.kt`

- [ ] **Step 1: Write failing lease tests**

Endpoints:

```text
POST /api/automation/materials/claims
POST /api/automation/materials/{requestId}/heartbeat
POST /api/automation/materials/{requestId}/complete
POST /api/automation/materials/{requestId}/fail
```

Claim response includes request ID, lease token, lease expiry, full vacancy snapshot, decrypted candidate profile, active tone examples, requested kinds, cover-letter-required flag, and route `TERRA` or `SOL_IMPROVE`. Completion is multipart metadata plus named artifact parts.

Assert `FOR UPDATE SKIP LOCKED`, only one live claim, lease token fencing, expired lease requeue, attempt cap, stale completion rejection, valid hash enforcement, and machine-scope authorization.

- [ ] **Step 2: Implement leases transactionally**

Use a 10-minute lease renewed every 60 seconds. After three infrastructure attempts, transition to `FAILED`. Validation failure follows product fallback rules and does not consume an infrastructure retry. Claim only when the automation runner health state allows Codex execution.

- [ ] **Step 3: Implement atomic completion**

Validate all metadata and artifact hashes first; persist revision + artifacts and transition request in one transaction. A completion retry with the same request/lease/manifest hash returns the existing revision. A different manifest under the same lease returns conflict.

- [ ] **Step 4: Add metrics without content labels**

Record queue depth, claim age, generation duration, validation failures by code, fallbacks, Sol repairs, and terminal outcome. Never label metrics with vacancy title, company, profile data, or generated text.

- [ ] **Step 5: Pass tests and commit**

Run:

```bash
./gradlew test --tests '*AutomationMaterialControllerIntegrationTest'
git add src/main/kotlin/com/mshykhov/jobhunter/application/materials src/main/kotlin/com/mshykhov/jobhunter/api/rest/automation src/main/kotlin/com/mshykhov/jobhunter/infrastructure/security/SecurityConfig.kt src/main/kotlin/com/mshykhov/jobhunter/infrastructure/metrics/AutomationMetrics.kt src/test/kotlin/com/mshykhov/jobhunter/api/rest/automation
git commit -m "feat(automation): add material generation leases"
```

## Phase 3: Generate and validate packages on the private runner

### Task 10: Extend the automation client and redact all material content

**Files:**
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/materials-client.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/types.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/__tests__/materials-client.test.ts`
- Modify: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/api/redaction.ts`
- Modify: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/config.ts`

- [ ] **Step 1: Write failing client and redaction tests**

Test no-work `204`, claim parsing, heartbeat, multipart completion, idempotent retry, lease conflict, and recursive redaction of `candidateProfile`, `vacancyDescription`, `coverLetter`, `recruiterMessage`, `derivedSource`, and binary buffers.

- [ ] **Step 2: Implement the typed client**

Reuse the current token provider and base request behavior. Add timeouts and abort signals. Keep content only in scoped local variables and never include full response bodies in thrown errors.

- [ ] **Step 3: Add config**

```text
MATERIALS_POLL_INTERVAL_MS=15000
MATERIALS_RENDERER_BIN=/opt/job-hunter-cv/bin/cv-materials-render
MATERIALS_WORK_DIR=/var/lib/job-hunter/materials
MATERIALS_TERRA_MODEL=gpt-5.6-terra
MATERIALS_SOL_MODEL=gpt-5.6-sol
```

Validate absolute renderer/work paths and exact supported model names. Do not accept an arbitrary model fallback.

- [ ] **Step 4: Pass tests and commit**

Run:

```bash
npm test -- src/materials/__tests__/materials-client.test.ts
git add src/materials src/api/redaction.ts src/config.ts
git commit -m "feat(materials): add runner queue client"
```

### Task 11: Implement a single structured Terra generation call

**Files:**
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/prompt-builder.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/codex-materials-generator.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/__tests__/prompt-builder.test.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/__tests__/codex-materials-generator.test.ts`
- Modify: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/codex/jsonl-parser.ts`

- [ ] **Step 1: Write failing prompt and process tests**

Assert exact model selection, `--ephemeral`, non-interactive execution, JSONL parsing, structured output schema, timeout/kill behavior, no shell interpolation, and no prompt/body logging. The prompt must explicitly require ID selection for CV and source fact IDs for free text.

- [ ] **Step 2: Build the bounded input**

Include:

- Full vacancy text and structured job metadata.
- Only the active public-safe candidate profile.
- Only tone examples relevant to requested message kinds.
- Fixed length/tone rules.
- An instruction to choose existing CV variant IDs rather than rewrite CV facts.
- An instruction that cover-letter/recruiter claims must cite source fact IDs and use no uncited number, technology, employer, achievement, or responsibility.

- [ ] **Step 3: Invoke Codex safely**

Equivalent command arguments:

```text
codex exec
--profile automation-canary
--ephemeral
--json
--sandbox read-only
--model gpt-5.6-terra
--output-schema /opt/job-hunter-automation/contracts/application-materials/v1/generation-output.schema.json
-C /var/lib/job-hunter/materials/empty-workspace
-
```

Pass the prompt through stdin with `spawn`, not as a shell string or command-line argument. Validate final JSON with Zod even after Codex schema validation. Save no Codex session.

- [ ] **Step 4: Pass tests and commit**

Run:

```bash
npm test -- src/materials/__tests__/prompt-builder.test.ts src/materials/__tests__/codex-materials-generator.test.ts
git add src/materials src/codex/jsonl-parser.ts
git commit -m "feat(materials): generate structured package selections"
```

### Task 12: Add deterministic truth, tone, ATS, and length validators

**Files:**
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/validation/validate-selection.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/validation/validate-claims.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/validation/validate-style.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/validation/validate-ats.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/validation/index.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/validation/__tests__/validators.test.ts`

- [ ] **Step 1: Write adversarial failing tests**

Reject:

- Unknown fact/variant/experience IDs or a variant under the wrong role.
- Changed locked fields or reordered employment chronology.
- Any uncited number, metric, technology, employer, certification, or responsibility in free text.
- Age, DOB, education, degree, university, language level, or a languages section.
- NDA-protected names configured in the private profile denylist.
- Cover letters outside the selected range or with more than three sentences.
- Recruiter messages outside 25-45 words.
- Empty pleasantries, exaggerated adjectives, generic enthusiasm, repeated vacancy wording, fake familiarity, or “AI assistant” phrasing.
- Keyword stuffing and skills not present in the profile.

- [ ] **Step 2: Implement closed-world claim validation**

For CV, reconstruct all visible content from approved variants; never accept generated CV prose. For messages, require cited fact IDs and ensure every extracted numeric token, capitalized proper noun, technology token, metric, and claim anchor is in the union of cited fact allowlists plus vacancy company/role terms. Return stable machine codes and JSON paths, for example:

```ts
type ValidationIssue = {
  code:
    | "UNKNOWN_VARIANT"
    | "UNSUPPORTED_NUMBER"
    | "UNSUPPORTED_TECHNOLOGY"
    | "FORBIDDEN_FIELD"
    | "COVER_LETTER_LENGTH"
    | "RECRUITER_MESSAGE_LENGTH"
    | "NON_HUMAN_TONE"
    | "KEYWORD_STUFFING";
  path: string;
  message: string;
  blocking: boolean;
};
```

- [ ] **Step 3: Implement ATS scoring as diagnostics, not fabrication pressure**

Report matched vacancy keywords, profile-backed missing keywords, selected variant coverage, and keyword density. Never penalize absence of a skill that is not in the candidate profile and never ask the model to add it.

- [ ] **Step 4: Pass tests and commit**

Run:

```bash
npm test -- src/materials/validation/__tests__/validators.test.ts
git add src/materials/validation
git commit -m "feat(materials): validate truth tone and ATS coverage"
```

### Task 13: Add one-shot Sol repair and product fallbacks

**Files:**
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/repair-policy.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/__tests__/repair-policy.test.ts`
- Modify: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/codex-materials-generator.ts`

- [ ] **Step 1: Write failing decision-table tests**

Decision table:

```text
valid first output                         -> no Sol
invalid optional recruiter message         -> omit, no Sol, package continues
invalid optional cover letter              -> omit, no Sol, package continues
invalid required cover letter              -> one Sol repair, then BLOCKED if invalid
invalid tailored CV selection/render       -> one Sol repair, then base CV fallback
explicit Improve with Sol                  -> exactly one Sol call and a new revision
owner text edit validation                 -> zero AI calls; validate and create child or reject
Codex auth/model/preflight failure          -> FAILED, no silent Terra/Sol substitution
```

- [ ] **Step 2: Implement bounded repair input**

Use `gpt-5.6-sol` with the same output schema, original structured input, the invalid output, and deterministic issue codes only. Explicitly forbid unrelated rewriting. Do not ask Sol to validate its own result; run the same deterministic validators once.

- [ ] **Step 3: Pass tests and commit**

Run:

```bash
npm test -- src/materials/__tests__/repair-policy.test.ts src/materials/__tests__/codex-materials-generator.test.ts
git add src/materials
git commit -m "feat(materials): add bounded Sol repair policy"
```

### Task 14: Orchestrate claim, generation, rendering, upload, and cleanup

**Files:**
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/renderer-adapter.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/materials-worker.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/materials-loop.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/__tests__/renderer-adapter.test.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/__tests__/materials-worker.test.ts`
- Modify: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/launcher.ts`
- Modify: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/index.ts`

- [ ] **Step 1: Write failing orchestration tests**

Use fakes for API, Codex, clock, and renderer. Test success, no work, heartbeat during long generation, lease loss cancellation, renderer timeout, hash mismatch, CV fallback, required cover-letter block, idempotent completion retry, crash recovery, and guaranteed work-directory cleanup.

- [ ] **Step 2: Implement renderer adapter**

Create a `0700` per-request directory under `MATERIALS_WORK_DIR`, write `render-request.json` with `0600`, invoke the absolute renderer binary without a shell, parse `manifest.json`, verify hashes locally, and reject files outside the request directory.

- [ ] **Step 3: Implement worker sequence**

```text
claim -> start lease heartbeat -> generate -> validate -> optional repair/fallback
      -> reconstruct derived CV source from approved variants -> render
      -> validate renderer manifest -> multipart complete -> stop heartbeat -> wipe workdir
```

Persist no prompt, profile, vacancy body, output, or artifact in application logs. On SIGTERM, stop claiming, finish or release the active lease within the configured shutdown window, and clean the request directory.

- [ ] **Step 4: Start the loop only after health preflight**

The existing launcher starts materials polling only when API auth, Codex auth/model, renderer binary, LibreOffice, Poppler, disk space, and automation delegation are healthy. Materials failure degrades the materials component without crashing browser/MCP health reporting.

- [ ] **Step 5: Verify and commit**

Run:

```bash
npm run verify
git add src/materials src/launcher.ts src/index.ts
git commit -m "feat(materials): run private package worker"
```

## Phase 4: Replace outreach with the manual Application Package UI

### Task 15: Add typed hooks and package status polling

**Files:**
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/materials/types.ts`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/materials/hooks/useApplicationMaterials.ts`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/materials/hooks/__tests__/useApplicationMaterials.test.tsx`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/lib/api.ts`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/mocks/handlers.ts`

- [ ] **Step 1: Write failing hook tests**

Test queue mutation, idempotent repeated click, 3-second polling only while non-terminal, stop on `READY|READY_WITH_FALLBACK|BLOCKED|FAILED`, artifact blob download, Sol improvement, owner-edit validation, revision selection, explicit package deletion, and query invalidation.

- [ ] **Step 2: Implement types and hooks following current TanStack patterns**

Do not call the API directly from components. Keep server status authoritative. Render validator codes into human messages in UI utilities, not the API contract.

- [ ] **Step 3: Pass and commit**

Run:

```bash
npm test -- src/features/materials/hooks/__tests__/useApplicationMaterials.test.tsx
git add src/features/materials src/lib/api.ts src/mocks/handlers.ts
git commit -m "feat(materials): add package API hooks"
```

### Task 16: Build the compact Application Package panel

**Files:**
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/materials/components/ApplicationMaterialsSection.tsx`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/materials/components/MaterialStatus.tsx`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/materials/components/RevisionHistory.tsx`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/materials/components/RevisionDiff.tsx`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/materials/components/ProvenanceDrawer.tsx`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/materials/components/__tests__/ApplicationMaterialsSection.test.tsx`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/jobs/components/JobEntryContent.tsx`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/jobs/components/JobGroupJobs.tsx`

- [ ] **Step 1: Write failing component tests**

Test:

- Empty state with one primary `Prepare application package` action.
- Optional checkboxes for cover letter and recruiter message, both enabled by default.
- A compact advanced toggle for `Cover letter is required`; only a confirmed owner/form requirement may raise the cap from 70 to 90 words.
- Queued/progress state without duplicate submission.
- Ready state with PDF/DOCX download and copy buttons.
- Very short cover letter shown in full, no large editor by default.
- `READY_WITH_FALLBACK` clearly labels base CV use.
- `BLOCKED` shows exact validation reason and retry action.
- Revision history never overwrites an earlier revision.
- Revision comparison shows selected/removed fact variants, ATS coverage changes, validation outcomes, and artifact hashes without trying to diff PDF bytes.
- Cover-letter/recruiter text can be edited and saved as a validated child revision; cancel leaves the parent untouched.
- An eligible historical revision can be selected explicitly; deleting the entire package requires a destructive confirmation naming the vacancy.
- Sol button creates a new revision and is disabled while work is active.
- Provenance drawer maps each selected CV line/message claim to fact IDs.

- [ ] **Step 2: Implement the panel in both job render paths**

Replace `OutreachSection` usage in `JobEntryContent.tsx` and `JobGroupJobs.tsx` with the same package component. Keep the visual footprint compact; generated text is a result, not a settings form.

- [ ] **Step 3: Verify desktop and mobile**

Run:

```bash
npm test -- src/features/materials/components/__tests__/ApplicationMaterialsSection.test.tsx
npm run build
```

Open the job detail at desktop width and 390x844. Verify buttons remain reachable, long filenames wrap, drawer content scrolls, and copy/download actions have accessible names.

- [ ] **Step 4: Commit**

Run:

```bash
git add src/features/materials src/features/jobs/components/JobEntryContent.tsx src/features/jobs/components/JobGroupJobs.tsx
git commit -m "feat(materials): add application package panel"
```

### Task 17: Add profile/tone administration without prompt engineering UI

**Files:**
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/materials/components/MaterialProfileSettings.tsx`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/materials/components/ToneExamplesEditor.tsx`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/materials/components/__tests__/MaterialProfileSettings.test.tsx`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/settings/components/SettingsPage.tsx`

- [ ] **Step 1: Write failing settings tests**

Show active profile hash/date/base CV validation, allow owner-only bundle upload, list previous immutable versions, and edit a small set of encrypted tone examples. Do not expose arbitrary system prompts or model-generated profile facts.

- [ ] **Step 2: Implement concise settings**

The UI may display `English C1` under private matching facts with “not rendered in documents”. It must not offer age, education, or languages-section fields. Model policy is read-only: Terra default, Sol one-shot repair.

- [ ] **Step 3: Verify and commit**

Run:

```bash
npm test -- src/features/materials/components/__tests__/MaterialProfileSettings.test.tsx
npm run build
git add src/features/materials src/features/settings/components/SettingsPage.tsx
git commit -m "feat(materials): add profile and tone settings"
```

## Phase 5: Migrate data, remove legacy, and verify end to end

### Task 18: Import old outreach text once and remove API legacy

**Files:**
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/LegacyOutreachImportService.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/infrastructure/materials/LegacyOutreachImportRunner.kt`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/test/kotlin/com/mshykhov/jobhunter/application/materials/LegacyOutreachImportServiceIntegrationTest.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/ai/OutreachGenerator.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/outreach/OutreachService.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/outreach/OutreachSettingsEntity.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/outreach/OutreachSettingsFacade.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/outreach/OutreachSettingsRepository.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/outreach/OutreachSourceConfig.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/job/dto/CoverLetterResponse.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/job/dto/RecruiterMessageResponse.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/settings/dto/OutreachSettingsResponse.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/settings/dto/OutreachSourceConfigRequest.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/settings/dto/OutreachSourceConfigResponse.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/settings/dto/OutreachTestRequest.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/settings/dto/SaveOutreachSettingsRequest.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/test/kotlin/com/mshykhov/jobhunter/application/outreach/OutreachServiceTest.kt`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/job/JobController.kt`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/settings/SettingsController.kt`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/userjob/UserJobEntity.kt`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/api/rest/job/dto/GroupJobResponse.kt`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/test/kotlin/com/mshykhov/jobhunter/api/rest/job/JobControllerIntegrationTest.kt`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/test/kotlin/com/mshykhov/jobhunter/api/rest/settings/SettingsControllerIntegrationTest.kt`

- [ ] **Step 1: Write the failing encrypted-import integration test**

Seed both old fields, run the import twice, and assert exactly two encrypted `LEGACY_IMPORTED` rows, successful owner-authorized decryption, no plaintext in the new table, and a completed marker whose source/import counts match. Assert the service refuses to mark completion if any non-empty source value has no import.

- [ ] **Step 2: Implement Release A import before deleting code paths**

V27 must also create `application_data_migrations(name, source_count, imported_count, completed_at)`. On application startup, `LegacyOutreachImportRunner` invokes the transactional service before materials claims are enabled. The service reads old columns with a narrow JDBC query, encrypts through `MaterialEncryptionService`, inserts idempotently by `(user_job_id, kind)`, verifies counts, then records `legacy-outreach-v1`. It never logs plaintext. Old outreach endpoints are disabled in the same Release A, but the physical columns and `outreach_settings` table remain until Release B.

- [ ] **Step 3: Remove endpoints and old application code**

Delete generation/test/settings endpoints and all old field mappings. Ensure legacy imports are read-only and excluded from `ensureReady`, worker claims, artifact downloads, and future submission selection.

- [ ] **Step 4: Prove no legacy API symbol remains**

Run:

```bash
rg -n 'OutreachGenerator|OutreachService|coverLetterPrompt|recruiterMessagePrompt|generate-cover-letter|generate-recruiter-message' src || true
./gradlew test
```

Expected: `rg` prints nothing; all API tests pass.

- [ ] **Step 5: Commit and deploy Release A**

Run:

```bash
git add -A src
git commit -m "refactor(materials): remove legacy outreach pipeline"
```

Deploy Release A through the normal API release path. Verify `application_data_migrations` contains `legacy-outreach-v1` with equal counts, all new packages work, and rollback no longer requires old endpoints. Do not create V28 before this production verification.

- [ ] **Step 6: Create and test Release B drop migration**

**Files:**
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/resources/db/migration/V28__remove_legacy_outreach_storage.sql`
- Create: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/test/kotlin/com/mshykhov/jobhunter/application/materials/LegacyOutreachDropMigrationIntegrationTest.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/application/materials/LegacyOutreachImportService.kt`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src/main/kotlin/com/mshykhov/jobhunter/infrastructure/materials/LegacyOutreachImportRunner.kt`

V28 must use a PostgreSQL `DO` block that raises an exception unless the completed marker exists and its counts match current encrypted imports. Then drop `user_jobs.cover_letter`, `user_jobs.recruiter_message`, and `outreach_settings`. The integration test must prove V28 fails without the marker and succeeds with a verified marker.

Run:

```bash
git fetch origin
git switch -c chore/remove-legacy-outreach-storage origin/master
./gradlew test --tests '*LegacyOutreachImportServiceIntegrationTest' --tests '*LegacyOutreachDropMigrationIntegrationTest'
git add -A src
git commit -m "chore(materials): drop verified outreach storage"
git push -u origin chore/remove-legacy-outreach-storage
```

Merge and deploy Release B separately. Verify API startup plus package generation before considering legacy storage removed.

### Task 19: Remove UI legacy and stale CV generators

**Files:**
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/jobs/components/OutreachSection.tsx`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/jobs/hooks/useOutreachGenerate.ts`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/settings/tabs/OutreachTab.tsx`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/settings/hooks/useOutreach.ts`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/settings/hooks/useOutreachTests.ts`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/settings/types/outreach.ts`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/settings/components/DefaultPromptsCard.tsx`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/settings/components/SourceConfigHeader.tsx`
- Delete: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/settings/components/SourceConfigPanel.tsx`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/jobs/types.ts`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/jobs/utils/__tests__/jobDetailUtils.test.ts`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/settings/components/SettingsPage.tsx`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/features/settings/types.ts`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/mocks/fixtures.ts`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src/mocks/settingsFixtures.ts`
- Delete: `/Users/myron/.worktrees/cv-application-materials/build/build_cv.py`
- Delete: `/Users/myron/.worktrees/cv-application-materials/build/build_roman_style.py`
- Modify: `/Users/myron/.worktrees/cv-application-materials/INDEX.md`

- [ ] **Step 1: Remove UI legacy only after package UI passes**

Run:

```bash
cd /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui
rg -n 'OutreachSection|useOutreach|coverLetter|recruiterMessage' src
```

Delete the old files and remove old fields from job DTO types, mocks, and tests. Keep the new material artifact kinds with explicit names such as `COVER_LETTER_TEXT`.

- [ ] **Step 2: Remove obsolete CV generators after reference scan**

Run:

```bash
cd /Users/myron/.worktrees/cv-application-materials
rg -n 'build_cv\.py|build_roman_style\.py|generate_docx\.py' . -g '!build/.venv/**'
```

Delete `build_cv.py`, `build_roman_style.py`, and the compatibility `generate_docx.py` after changing every caller to `python -m cv_materials.render_cli`. Then scan `/Users/myron/Library/LaunchAgents`, `/Users/myron/IdeaProjects/job-hunter-automation`, `/Users/myron/.zshrc`, `/Users/myron/.zprofile`, `/Users/myron/brain`, and both CV repositories for `/Users/myron/IdeaProjects/cv/generate` references. Update every live reference to `/opt/job-hunter-cv/bin/cv-materials-render`, rerun the referenced workflow, and delete the tracked stale Typst directory with `git -C /Users/myron/IdeaProjects/cv rm -r generate`. Commit that deletion in the stale CV repository as `refactor(build): remove unused Typst generator`.

- [ ] **Step 3: Verify and commit in both repos**

Run:

```bash
cd /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui && npm run lint && npm run format:check && npm test && npm run build && npm run rulesync:verify
cd /Users/myron/.worktrees/cv-application-materials && python3 -m pytest -q && ./build/build.sh
git -C /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui add -A
git -C /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui commit -m "refactor(materials): remove legacy outreach UI"
git -C /Users/myron/.worktrees/cv-application-materials add -A
git -C /Users/myron/.worktrees/cv-application-materials commit -m "refactor(build): remove legacy CV generators"
```

### Task 20: Add a realistic private evaluation corpus and end-to-end acceptance test

**Files:**
- Create: `/Users/myron/.worktrees/cv-application-materials/evals/vacancies/strong-backend-role.txt`
- Create: `/Users/myron/.worktrees/cv-application-materials/evals/vacancies/partial-match-role.txt`
- Create: `/Users/myron/.worktrees/cv-application-materials/evals/vacancies/required-cover-letter.txt`
- Create: `/Users/myron/.worktrees/cv-application-materials/evals/expected.yaml`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/scripts/materials-smoke.ts`
- Create: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src/materials/__tests__/materials-e2e.test.ts`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/README.md`
- Modify: `/Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/README.md`
- Modify: `/Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/README.md`
- Modify: `/Users/myron/.worktrees/cv-application-materials/README.md`
- Modify: `/Users/myron/IdeaProjects/job-hunter/README.md`

- [ ] **Step 1: Create private eval cases from sanitized real patterns**

Include at least 12 vacancies spanning Kotlin/Java backend, platform engineering, BFF, payments, weak matches, unsupported required skills, global-remote constraints, and mandatory cover letters. Store vacancy text only in the private CV repo. Expected assertions use fact/variant IDs, prohibited claims, length bounds, and package outcome, not exact generated prose.

- [ ] **Step 2: Run deterministic integration without live Codex**

Start API/PostgreSQL, use a fake Codex JSONL process and fake renderer, import a synthetic profile, queue through owner endpoint, claim through machine endpoint, complete, download, verify hashes, regenerate, and verify revision 1 remains unchanged.

- [ ] **Step 3: Run one live private smoke test**

On the LXD runner with real `auth.json` and renderer runtime:

```bash
npm run materials:smoke -- --vacancy /opt/job-hunter-cv/evals/strong-backend-role.txt
```

Expected:

- One Terra generation call.
- No Sol call for a valid result.
- CV is at most two pages and contains only approved variants.
- Cover letter is 30-70 words and reads like a direct human note.
- Recruiter message is 25-45 words.
- Age, education, and languages are absent.
- API stores a ready immutable revision with matching hashes.
- Runner logs contain no private text.

- [ ] **Step 4: Run one forced repair/fallback smoke test**

Feed a fixture with a deterministically invalid required letter and an invalid tailored CV. Verify one Sol call maximum, then either a valid repaired letter or `BLOCKED`, and base-CV fallback for the CV. Verify there is no third AI call.

- [ ] **Step 5: Update documentation**

Document:

- How to edit/profile facts safely and approve variants.
- How to export/import a profile version.
- How to install and preflight the private renderer.
- Environment variable names only, never values.
- State machine, fallback policy, model-cost policy, encryption/key rotation procedure, restore procedure, retention policy, and operator troubleshooting.
- Manual UI flow and the future `ensureReady`/submitted-revision integration contract.

- [ ] **Step 6: Run complete verification**

Run:

```bash
cd /Users/myron/.worktrees/cv-application-materials && python3 -m pytest -q && ./build/build.sh
cd /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api && ./gradlew test
cd /Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials && npm run verify
cd /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui && npm run lint && npm run format:check && npm test && npm run build && npm run rulesync:verify
```

Expected: all suites pass; CV visual inspection passes; no private eval/profile/artifact content is staged in any public repository.

- [ ] **Step 7: Commit documentation and eval tooling in their owning repositories**

Use atomic Conventional Commits. Do not add AI attribution trailers. Do not push until the cross-repository review below passes.

## Phase 6: Cross-repository review and delivery

### Task 21: Audit security, contracts, generated artifacts, and Git state

**Files:**
- Review all changes in the four feature worktrees
- Modify only files required to fix findings

- [ ] **Step 1: Run the check-changes skill in each repository**

Review from each merge base through HEAD, including untracked files. Specifically inspect authentication boundaries, lease fencing, encryption failure behavior, content logging, archive/path traversal, subprocess arguments, file modes, temp cleanup, model substitution, and fallbacks.

- [ ] **Step 2: Scan public repositories for leaked private content and generated files**

Run:

```bash
rg -n 'myronshykhov@gmail\.com|\+380995173706|Under NDA|English C1' \
  /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api \
  /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui \
  /Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials \
  -g '!**/.git/**' || true
find /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api \
     /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui \
     /Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials \
  -type f \( -name '*.pdf' -o -name '*.docx' -o -name 'auth.json' \) -print
```

Expected: no real candidate content, CV artifacts, or credentials in public repositories. Synthetic fixtures are clearly fictional.

- [ ] **Step 3: Verify no placeholders or legacy symbols remain**

Run:

```bash
rg -n 'TODO|TBD|FIXME|NotImplemented|OutreachGenerator|OutreachService|coverLetterPrompt|recruiterMessagePrompt' \
  /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api/src \
  /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui/src \
  /Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials/src \
  /Users/myron/.worktrees/cv-application-materials/src || true
```

Expected: no unresolved implementation placeholders or old outreach pipeline symbols.

- [ ] **Step 4: Verify contract consistency**

Compare schema version, enums, status transitions, artifact kinds, validation codes, hash algorithm, and media types across Python, Kotlin, TypeScript runner, and React. Add a golden synthetic round-trip test for any mismatch found.

- [ ] **Step 5: Re-run all verification after fixes**

Repeat the four commands from Task 20 Step 6. Capture the exact passing output in the handoff.

- [ ] **Step 6: Push feature branches and update coordinator gitlinks**

Push non-force:

```bash
git -C /Users/myron/.worktrees/cv-application-materials push -u origin feat/application-materials
git -C /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-api push -u origin feat/application-materials
git -C /Users/myron/IdeaProjects/.worktrees/job-hunter-automation-materials push -u origin feat/application-materials
git -C /Users/myron/IdeaProjects/job-hunter/.worktrees/materials-ui push -u origin feat/application-materials
```

Merge through each repository's normal PR flow. Then create a clean coordinator worktree from current `origin/master`, update the API/UI/automation gitlinks to the merged commits, align root docs, run Rulesync verification if canonical config changed, commit `feat: integrate application materials compiler`, and push non-force.

## Acceptance checklist

- [ ] A profile bundle can be exported from `/Users/myron/cv`, imported, versioned, and restored without raw note discovery.
- [ ] Manual `Prepare application package` produces a revision unattended through the private runner.
- [ ] The tailored CV uses only approved variants, stays within two pages, and falls back to the validated base CV when needed.
- [ ] Cover letters are normally 40-60 words, always within the selected 30-70/90-word policy, and sound direct and human.
- [ ] Recruiter messages are 25-45 words and non-blocking.
- [ ] English C1 is available to matching/forms but absent from rendered materials; age and education are absent everywhere.
- [ ] One Terra call is the normal path; one Sol call is the absolute repair/improvement limit; deterministic validation always makes the final decision.
- [ ] Every visible claim has profile provenance; unknown facts, variants, metrics, technologies, and protected names are rejected.
- [ ] Package revisions and artifacts are immutable, encrypted at rest, hash-verified, owner-isolated, and content-free in logs.
- [ ] The UI provides status, revision history, provenance, downloads, copy actions, fallback labels, and one explicit Sol improvement.
- [ ] Old outreach generation/settings/UI and unused CV generators are removed only after migration and replacement verification.
- [ ] The API exposes `ensureReady` and revision/hash metadata needed by future browser automation, without pretending website submission exists in this delivery.
