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
