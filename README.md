# GameWiki

![version](https://img.shields.io/badge/version-0.13.0-blue) ![schema](https://img.shields.io/badge/schema-7-informational)

A small, self-hosted wiki for documenting games — pages you write, versioned,
cross-linked, and searchable. Python and FastAPI on Postgres, run under Docker
Compose.

Reads are public. Writes need a signed-in account on an allowlist. Every edit
is kept forever.

## Quickstart

```bash
cp .env.example .env      # optional — Compose supplies working defaults
docker compose up -d --build
curl -s http://localhost:8000/health
```

Then open <http://localhost:8000>. The stack is three services: the `app`, a
`db` (Postgres 16), and `oidc` — a stub identity provider from
`devtools/fake_oidc.py` that approves every sign-in, so local development and
CI never reach the public internet. **It must never be deployed.** In
production, point `OIDC_DISCOVERY_URL` at a real provider; it defaults to
Google.

```bash
docker compose exec app pytest -q          # 193 tests
docker compose exec app ruff check .
python3 scripts/check_release.py           # version/changelog/schema consistency
```

## What it does

| | |
|---|---|
| **Pages** | Slug-addressed, markdown bodies, created and edited in the browser or over JSON. |
| **History** | Every version kept, addressable, and attributed. Concurrent edits are caught by an `If-Match` revision check rather than silently clobbering. |
| **Wiki links** | `[[Page Title]]` resolves between pages; a link to a page that doesn't exist yet is a red link that doubles as an invitation to write it. Each page lists what links to it. |
| **Search** | Postgres full-text over titles and bodies, ranked, with highlighted snippets. |
| **Accounts** | Google OIDC sign-in. Roles are `reader`, `editor`, `admin`, with an email/domain allowlist and an admin screen. Role changes are audited. |

## How it fits together

| Module | Does |
|---|---|
| `app/main.py` | App setup, `/health`, migrations at startup, the 401-vs-403 split. |
| `app/pages.py` | The JSON API under `/pages`. |
| `app/web.py` | The browser UI — `/`, `/w/{slug}`, `/new`, `/search`. |
| `app/repository.py` | All data access, speaking in domain errors so both surfaces share it. |
| `app/markup.py` | Markdown, wiki links, search snippets — everything that renders untrusted text. |
| `app/auth.py`, `app/csrf.py`, `app/admin.py` | Sign-in, CSRF tokens, account administration. |
| `app/docs.py` | This documentation, served at `/docs`. |
| `app/migrations/` | Numbered SQL, applied in order at process start. |

Two invariants worth knowing before changing anything:

- **`app/version.py` is the only place a version number lives.** `/health`
  reports it, and CI fails a commit that didn't bump it.
- **`SCHEMA_VERSION` must equal the number of migration files.** A mismatch is
  a hard boot failure, not a warning.

## Security posture

Page bodies are user-authored and reach the browser as HTML, so that pipeline
is written for hostile input: markdown with raw HTML disabled, a link-scheme
validator, and nh3 sanitising on top. Search snippets take the same route.
Forms carry CSRF tokens; the JSON API doesn't, because a cross-site form can't
send `application/json` — a property the suite asserts rather than assumes.

Known gaps are listed per release in the [changelog](CHANGELOG.md). The largest
today: role changes only take effect at the affected user's next sign-in, and
sign-in has never been verified against real Google.

## Documentation

Everything reader-facing is indexed at [`docs/index.md`](docs/index.md), served
at `/docs` on a running instance.

- [Changelog](CHANGELOG.md) — every release and the reasoning behind it.
- [Project guidelines](CLAUDE.md) — the conventions this repo is built to.
