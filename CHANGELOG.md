# Changelog

All notable changes to GameWiki are recorded here, newest first.

**How to add an entry.** Every commit ships a version bump, and every bump gets
one entry at the top of this file — see the changelog rules in
[CLAUDE.md](CLAUDE.md). The format is
`## [X.Y.Z] - YYYY-MM-DD — "Fun Name"` (UTC date, Fun Name required and unique),
followed by `**Commit summary:**`, `**Description:**`, and at least one
categorised list (`### Added`, `### Changed`, `### Fixed`, `### Removed`,
`### Security`). The Fun Name must match `APP_VERSION_NAME` in `app/version.py`
and the git commit subject.

---

## [0.5.1] - 2026-08-03 — "The Turnstile"

**Commit summary:** add the CI workflow and a release-metadata checker.

**Description:** The branch had no automatic regression gate — 34 tests only
ran when someone remembered to run them. GitHub Actions now runs on push to
`main` and on every pull request.

Two jobs run in parallel. **Tests and lint** builds the Compose stack, waits for
healthy, asserts the running `/health` version matches the source tree, then
runs pytest and both ruff checks, dumping container logs on failure. **Release
metadata** runs `scripts/check_release.py`, which enforces the four rules
CLAUDE.md states but nothing could previously catch: the changelog's top entry
matches `APP_VERSION`, its Fun Name matches `APP_VERSION_NAME`,
`SCHEMA_VERSION` equals the migration-file count, and — given a base ref — the
version actually moved. Those are exactly the rules a reviewer skims past, so
they belong in CI rather than in a reader's memory.

The checker is runnable locally as `python3 scripts/check_release.py`, which is
the point: catch it before the commit, not after the push.

**Lint scope moved off `exec`.** The first draft ran ruff via `docker compose
exec app`, which lints `/srv` — and the image only carries `app/` and `tests/`.
That silently excluded `scripts/` and anything new at the repo root; ruff found
two real violations in `check_release.py` that the container-side lint reported
as clean. Both lint steps now bind-mount the checked-out tree instead, so CI
lints what is actually committed.

Nothing about the app changed — no source, schema, or endpoint is touched, so
`SCHEMA_VERSION` stays at `2`.

**Unverified:** the workflow itself has never executed. It is written against
`ubuntu-latest`'s bundled Docker Compose and cannot run on this machine; the
first push is its first real test. `scripts/check_release.py` was run locally
against this working tree and passes, including the `--base` bump check against
`HEAD`.

### Added

- `.github/workflows/ci.yml` — `release-check` and `test` jobs on push to `main`
  and on pull requests.
- `scripts/check_release.py` — changelog/version/fun-name/schema consistency,
  plus an optional `--base <ref>` check that the version was bumped. Exercised
  locally against both failure paths: an unbumped version and a
  `SCHEMA_VERSION` that disagrees with the migration count.

### Changed

- `app/version.py`: `APP_VERSION` `0.5.0` → `0.5.1`, `APP_VERSION_NAME` →
  `"The Turnstile"`.
- `CLAUDE.md`: the integration-test section's CI paragraph now names the
  workflow, its triggers, and what each job enforces, replacing the placeholder
  saying no CI existed.

---

## [0.5.0] - 2026-08-03 — "The Reading Room"

**Commit summary:** add the server-rendered browser UI — page list, page view,
history, and an edit form with conflict handling.

**Description:** GameWiki is usable without curl. Jinja templates and a base
stylesheet render the wiki under `/w/`, kept clear of the API's `/pages/`
namespace so the two never collide.

The edit form carries the revision it started from in a hidden field, which
becomes the optimistic-concurrency check on save — the form equivalent of
`If-Match`. **A conflict re-renders the form with the editor's draft intact**
rather than discarding it, shows what happened, and advances the hidden field
to the current revision so a deliberate re-save can land. Losing an editor's
typing to a 409 page would have made the concurrency check worse than not
having one.

**Scope note:** the approved sketch listed four routes. Creating a page was not
among them, which would have left the UI unable to add content — so `GET`/`POST
/new` are included, along with `/w/{slug}/history` and
`/w/{slug}/revisions/{n}`, since "page view with history" needs somewhere for
the history link to go.

To keep the HTML and JSON surfaces from duplicating SQL, reads and writes moved
into a new `app/repository.py` speaking in domain errors. `app/pages.py` is now
purely the HTTP contract over it — same endpoints, same responses, no behaviour
change.

Page bodies are **plain text**, rendered with `white-space: pre-wrap`. No
markdown, no wiki links, no search, and no authentication — anyone who can
reach the app can edit any page.

Verified end to end: rebuild reaches healthy, `/health` reports `0.5.0` /
"The Reading Room", `pytest -q` passes 34 tests (up from 19), ruff clean.
Rendered a real page through the form and confirmed the markup, the footer
version stamp, and that user-supplied `<script>` in a title and `<img onerror>`
in a body come back HTML-escaped. **Not** verified in a real browser — no
browser is available on this machine, so layout and the touch targets are
asserted in CSS and smoke tests rather than seen.

### Added

- `app/web.py` — the HTML routes:
  - `GET /` → page list, ordered by title, with a New page action.
  - `GET /new`, `POST /new` → create a page; 400 re-renders with the draft kept
    on a malformed slug, a blank title, or a duplicate slug.
  - `GET /w/{slug}` → rendered page with Edit and History actions; 404 unknown.
  - `GET /w/{slug}/edit` → form with the revision in a hidden field.
  - `POST /w/{slug}/edit` → 303 redirect on success; **409** re-render with the
    draft preserved when the page moved on.
  - `GET /w/{slug}/history` → revisions newest first.
  - `GET /w/{slug}/revisions/{n}` → read-only historical version.
- `app/templates/` — `base.html` (nav, container, footer version stamp),
  `index.html`, `page.html`, `edit.html`, `new.html`, `history.html`,
  `revision.html`. Autoescaping is on, so page content can't inject markup.
- `app/static/base.css` — the base stylesheet. Global `button` rule sets
  `min-height: 44px` with `inline-flex` centring; `input` / `select` set
  `min-height: 44px`; nav links and list rows are padded to the same baseline.
  These are the rules CLAUDE.md names as load-bearing.
- `app/repository.py` — shared data access raising `PageNotFound`,
  `RevisionNotFound`, `SlugTaken`, and `RevisionConflict`.
- `tests/api/test_web.py` — 15 smoke and contract tests: every route returns
  200 with its heading and the nav, plus the 404s, the conflict re-render, the
  duplicate-slug and malformed-slug rejections, and an assertion that the 44px
  rules are still served in the stylesheet.
- Dependencies: `jinja2`, `python-multipart`.
- `/static` mount on the app.

### Changed

- `app/version.py`: `APP_VERSION` `0.4.0` → `0.5.0`, `APP_VERSION_NAME` →
  `"The Reading Room"`. The name now genuinely feeds an in-UI version stamp.
- `app/pages.py`: SQL moved out to `app/repository.py`; the module now maps
  domain errors to status codes. No change to any endpoint's behaviour.

---

## [0.4.0] - 2026-08-03 — "Nothing Is Lost"

**Commit summary:** add revision history and optimistic concurrency on page
edits.

**Description:** Closes the data-loss gap left open by 0.3.0. Every version of
a page is now recorded in `page_revisions`, and `PUT` appends rather than
destroys. `SCHEMA_VERSION` goes to `2`.

**History starts at creation, not at the first edit.** The approved sketch had
`PUT` snapshot the *prior* text, which would leave a never-edited page with an
empty history and make revision numbers lag the edit count. Instead `POST`
writes revision 1 and each `PUT` appends revision N+1, so `revisions/{n}` is
addressable for every version including the current one. The prior text is
preserved either way — this just makes the history complete.

`pages.revision` is a denormalised pointer at the latest revision and doubles
as the ETag, which is served on `POST`, `GET`, and `PUT` responses. `PUT`
accepts an optional `If-Match`: supply the revision you read and a racing edit
is rejected instead of clobbering. **`If-Match` is optional, so a client that
omits it still gets last-write-wins** — the prior text survives in the history,
but the conflict is not surfaced. Requiring it would be a breaking change and
belongs in its own bump.

**Conflicts return 409, not 412.** RFC 9110 specifies 412 Precondition Failed
for a failed `If-Match`. This project uses 409 to match the edit-conflict
convention already named in CLAUDE.md's test contract. Worth revisiting if a
generic HTTP client ever consumes the API.

The check-then-write in `PUT` runs inside a transaction with `SELECT … FOR
UPDATE`, so two concurrent edits can't both observe the same revision and pass
the precondition.

Verified end to end: migration 002 applied at startup and backfilled revision 1
for all 10 pre-existing pages, `/health` reports `0.4.0` / "Nothing Is Lost" /
`schema_version: 2`, `pytest -q` passes 19 tests (up from 11), ruff clean.
Manually confirmed the ETag headers, that a stale `If-Match` returns 409, and
that the losing write leaves no trace.

### Added

- `app/migrations/002_create_page_revisions.sql` — `page_revisions`
  (`page_id` FK cascade, `revision`, `title`, `body`, `created_at`, unique on
  `(page_id, revision)`), a `revision` column on `pages`, and a backfill making
  every pre-existing page its own revision 1.
- `GET /pages/{slug}/revisions` → 200, newest first, summaries (revision, title,
  created_at — no body); 404 on unknown slug.
- `GET /pages/{slug}/revisions/{n}` → 200 with the full text of that version;
  404 on unknown slug or unknown revision.
- `If-Match` support on `PUT /pages/{slug}` → **409** when the named revision
  isn't current, **400** when the header is malformed. Accepts `"3"`, `W/"3"`,
  and a bare `3`.
- `ETag` response header on `POST /pages`, `GET /pages/{slug}`, and
  `PUT /pages/{slug}`.
- Eight tests in `tests/api/test_pages.py` covering the concurrency and history
  surfaces, including one asserting the original text is still readable after an
  overwrite.

### Changed

- `app/version.py`: `APP_VERSION` `0.3.0` → `0.4.0`, `APP_VERSION_NAME` →
  `"Nothing Is Lost"`, `SCHEMA_VERSION` `1` → `2`.
- **Response shape:** `Page` and `PageSummary` now carry `revision`. Clients
  asserting on an exact key set need updating — the existing tests were.
- `POST /pages` now writes its revision row in the same transaction as the page,
  so a failed insert can't leave a page without history.

---

## [0.3.0] - 2026-08-03 — "The Binding"

**Commit summary:** add the pages table, the first migration, and slug-keyed
CRUD endpoints.

**Description:** The first real feature — GameWiki can now hold pages. A
`pages` table lands via the project's first migration, applied at process start
by a runner that tracks applied files in `schema_migrations`. `SCHEMA_VERSION`
goes to `1`, and startup now **hard-fails** if the applied-migration count and
`SCHEMA_VERSION` disagree, so the constant can't silently drift from the
migrations directory.

Pages are addressed by `slug` throughout. The surrogate `id` column exists for
referential use but is never exposed through the API, so clients and tests are
unaffected by a reseed.

Two deliberate omissions. There is **no DELETE endpoint** — the approved surface
was list/create/read/update, so tests generate a unique slug per run instead of
cleaning up, and page rows accumulate in the dev database. There is also **no
revision history**; `updated_at` is overwritten in place by `PUT`, so an edit
loses the prior text. Both are the natural next bumps.

Verified end to end: rebuild reaches healthy, `/health` reports `0.3.0` /
"The Binding" / `schema_version: 1`, the migration is recorded in
`schema_migrations` with the expected table and indexes, `pytest -q` passes 11
tests (up from 2), and ruff check and format are clean.

### Added

- `app/migrations/001_create_pages.sql` — `pages` with `id`, `slug` (unique),
  `title`, `body`, `updated_at`, plus a title index.
- `app/db.py` — a psycopg connection pool with a `dict_row` factory, and
  `run_migrations()`, which applies unapplied `.sql` files in filename order and
  returns the total applied count.
- `app/pages.py` — the `/pages` router:
  - `GET /pages` → 200, summary list (slug, title, updated_at — no body),
    ordered by title.
  - `POST /pages` → 201 with the full page; **409** on a duplicate slug; 422 on
    a missing title or a malformed slug (lowercase, digits, single hyphens).
  - `GET /pages/{slug}` → 200 with the full page; **404** on unknown slug.
  - `PUT /pages/{slug}` → 200 with the updated page and a refreshed
    `updated_at`; **404** on unknown slug.
- `tests/api/test_pages.py` — nine tests covering every happy path plus the 409,
  both 404s, and both 422s.
- Dependencies: `psycopg[binary]`, `psycopg-pool`.

### Changed

- `app/version.py`: `APP_VERSION` `0.2.0` → `0.3.0`, `APP_VERSION_NAME` →
  `"The Binding"`, `SCHEMA_VERSION` `0` → `1`.
- `app/main.py`: a lifespan hook opens the pool, runs migrations, and raises on
  schema drift before the app serves traffic. Mounts the pages router.

---

## [0.2.0] - 2026-08-02 — "The First Shelf"

**Commit summary:** scaffold the Docker Compose stack with a FastAPI app and a
`/health` endpoint reporting the running version.

**Description:** Turns the conventions settled in 0.1.0 into a running stack. An
`app` service (FastAPI on uvicorn) and a `db` service (Postgres 16) come up
under Compose, both with healthchecks, with `app` gated on `db` being healthy.
`GET /health` returns the version constants from `app/version.py`, which makes
the rebuild rule enforceable: poll the endpoint after a bump and a stale
container is immediately visible.

The app does not connect to Postgres yet — the service is in place so the page
schema can land without a Compose change, and `SCHEMA_VERSION` stays at `0`
until the first migration.

Verified end to end: `docker compose up -d --build app` builds and reaches
healthy, `/health` reports `0.2.0` / "The First Shelf", `pytest -q` passes 2
tests, and `ruff check` / `ruff format --check` are clean.

### Added

- `docker-compose.yml` — `app` (build from local Dockerfile, port 8000) and `db`
  (postgres:16-alpine, named `pgdata` volume), both with healthchecks.
  `DATABASE_URL` and `GAMEWIKI_BASE_URL` are supplied as internal Compose URLs.
- `Dockerfile` — python:3.12-slim, dependency layer split from source so edits
  don't reinstall.
- `pyproject.toml` — hatchling build, version read from `app/version.py` via
  regex so the manifest never carries a duplicate version string. Deps: fastapi,
  uvicorn; dev extras: httpx, pytest, ruff. Ruff and pytest config live here.
- `app/main.py` — the FastAPI app and `GET /health`, returning `status`,
  `version`, `version_name`, and `schema_version`.
- `app/__init__.py`.
- `tests/conftest.py` — session `base_url` fixture reading `GAMEWIKI_BASE_URL`
  (default `http://localhost:8000`) and an httpx `client` fixture. The suite
  talks to the running app over the network, per the integration-test rule.
- `tests/api/test_health.py` — the canonical test for this project. Happy path
  asserts status, exact body shape, and that the reported version matches the
  source tree; error path asserts an unknown path returns 404, guarding against
  a future page router mounted at the root swallowing them.
- `.env.example` — both env vars, commented, noting Compose sets them.
- `.gitignore` — Python and tooling caches, `.env`.

### Changed

- `app/version.py`: `APP_VERSION` `0.1.0` → `0.2.0`, `APP_VERSION_NAME` →
  `"The First Shelf"`. `SCHEMA_VERSION` unchanged at `0`.
- `CLAUDE.md`: the rebuild/test/lint commands are now verified rather than
  intended, and the rebuild section names `GET /health` as the concrete poll
  target with example output.

---

## [0.1.0] - 2026-08-02 — "The Empty Codex"

**Commit summary:** resolve the CLAUDE.md setup checklist, add the version home
and this changelog.

**Description:** GameWiki is a Python web app run under Docker Compose, serving
DB-backed wiki pages that document information about games. This release settles
the project's conventions before any application code exists: `app/version.py`
is established as the single source of truth for `APP_VERSION`,
`APP_VERSION_NAME`, and `SCHEMA_VERSION`; this changelog becomes the standalone
release log; and the guidelines file is pruned so every remaining **Applies if:**
gate is true for this project.

No application code ships in this release — the scaffold (`docker-compose.yml`,
`pyproject.toml`, the app package, the test suite) is still to come, and the
three commands recorded in CLAUDE.md are intended conventions rather than
verified ones until it lands.

### Added

- `app/version.py` as the version home, holding `APP_VERSION` (`0.1.0`),
  `APP_VERSION_NAME` (`"The Empty Codex"`), and `SCHEMA_VERSION` (`0`).
- `CHANGELOG.md` — this file — with the entry-format preamble.

### Changed

- `CLAUDE.md`: resolved every setup-checklist item. Recorded the project shape
  (Python + Docker Compose, DB-backed wiki pages), the version home, and the
  rebuild / test / lint commands. Made the gated sections concrete — the rebuild
  command, the `git push origin main` branch, the page-revision examples in the
  test-contract and compact-UI rules, and a note that wiki page content is data
  rather than documentation for the docs-index rule.

### Removed

- `CLAUDE.md`: the single-file-project version provision (GameWiki is a
  multi-file app) and the license-perimeter section (pages are user-authored;
  no third-party licensed dataset is redistributed). The latter should be
  restored if GameWiki ever ingests a licensed game dataset.
