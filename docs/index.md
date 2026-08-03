# Documentation

Every reader-facing document in this repo, grouped by type. A doc that is not
listed here is not reachable — the docs-index rule in
[CLAUDE.md](CLAUDE.md) requires the index row to land in the same commit as the
document itself.

On a running instance this page is served at `/docs`, and each row below is a
link to the rendered document.

## Repo documentation

| Document | Served at | Status | What it covers |
|---|---|---|---|
| [README](README.md) | `/docs/readme` | ✅ shipped | What GameWiki is, how to run it, and how the pieces fit together. |
| [Changelog](CHANGELOG.md) | `/docs/changelog` | ✅ shipped | Every release, newest first, with the reasoning behind each one. |
| [Project guidelines](CLAUDE.md) | `/docs/guidelines` | ✅ shipped | The conventions this repo is built to — versioning, tests, touch targets. |

## Guides

None yet. An operator guide — deploying against real Google, backups, restoring
a database — is the obvious first one.

## Design plans

None yet.

## References

None yet.

## Adding a document

1. Write it, under `docs/` or at the repo root.
2. Add a row to the right table above.
3. Add it to `DOCS` in `app/docs.py`, which is both the route allowlist and the
   source for the rendered index at `/docs`.
4. Add a smoke test to `tests/api/test_docs.py` — the per-slug parametrisation
   covers status, the H1, and the nav automatically once the slug is in `DOCS`.

Status vocabulary is fixed: `✅ shipped`, `🟠 partial`, `⚪ proposed`,
`⚪ design only`.
