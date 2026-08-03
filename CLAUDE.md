# GameWiki — Claude Code guidelines

## How to use this file

GameWiki is a **Python web app, run under Docker Compose**, serving wiki pages
that document information about games. Pages are user-authored and DB-backed.

The setup checklist has been walked and every **Applies if:** gate resolved for
this project. Sections whose gate was false are deleted, not left in place — a
rule that doesn't apply is worse than no rule, because it trains the reader to
skim past gates. **If a future section is added, gate it the same way.**

**Resolved project facts:**

| Fact | Value |
|---|---|
| Version home | `app/version.py` — `APP_VERSION`, `APP_VERSION_NAME`, `SCHEMA_VERSION` |
| Changelog | Standalone `CHANGELOG.md` at the repo root |
| Rebuild | `docker compose up -d --build app` |
| Test | `docker compose exec app pytest -q` |
| Lint | `docker compose exec app ruff check .` and `ruff format --check .` |

*All three commands are live and verified against the scaffold. Keep this table
true — if a command changes, it changes here in the same commit.*

**Deleted as not applicable:** the single-file-project version provision (this is
a multi-file app) and the license-perimeter section (GameWiki hosts
user-authored pages; it does not redistribute third-party licensed game
datasets). *If GameWiki ever ingests a licensed dataset — IGDB, MobyGames, a
wiki dump — restore the license-perimeter rules before the data lands.*

**Not yet built:** there is no `docs/` index page yet. The first commit that adds
a reader-facing doc must create the index in the same commit and backfill rows
for the existing repo-root docs, per the docs-index rule below.

Rules with no gate — versioning discipline, commit/push discipline, the
changelog format, and the multiple-choice convention — apply regardless of stack.

---

## Always update the changelog and version when making changes

**Applies if:** always.

**Every commit ships its own version bump.** One conceptually-distinct change =
one commit = one version bump = one CHANGELOG entry. No batching unrelated edits
into a single release: if you fix three unrelated bugs in a session, ship three
commits at e.g. `1.11.1`, `1.11.2`, `1.11.3` — not one commit at `1.11.0` listing
all three under `### Fixed`. The only thing that may legitimately span multiple
files in a single commit is a single coherent change (one feature, one bug, one
refactor) that needs the multi-file edit to be reviewable. Read the changelog in
full at the start of any version-related work.

### Where the version lives

**`app/version.py` is the single source of truth. Do not edit version numbers
anywhere else.** It is a dedicated module read by the app at runtime:

```python
"""GameWiki version constants — the single source of truth."""

APP_VERSION = "0.1.0"
APP_VERSION_NAME = "The Empty Codex"
SCHEMA_VERSION = 0
```

Nothing else — not `pyproject.toml`, not a Dockerfile label, not a template —
carries a hardcoded version string. Anything that needs the version imports it
from here.

### Bump rules

**Pick the highest bump that applies** — every commit bumps at least PATCH:

- **PATCH** (`0.0.x`) — **the default**. Bumps on every commit, including pure
  bug fixes, copy tweaks, comment-only edits, refactors with no behavior change,
  dependency updates, doc edits, etc. There is no such thing as a "no bump"
  commit.
- **MINOR** — new backward-compatible feature or additive schema change. (A
  MINOR bump satisfies the "every commit ships a bump" rule too — you don't bump
  PATCH on top.)
- **MAJOR** — breaking API/config/schema change that requires operator action.
  (Same — replaces the PATCH bump for that release. **Also triggers the
  changelog-archive rule below.**)

`SCHEMA_VERSION` lives alongside `APP_VERSION` and increments by **+1** for every
migration added. It moves independently of the semver bump — a MINOR feature
release that adds one migration bumps `APP_VERSION` MINOR and `SCHEMA_VERSION`
by one.

### Changelog entry format

- Add a new `## [X.Y.Z] - YYYY-MM-DD — "Fun Name"` section at the **top** of
  `CHANGELOG.md` (below the instructions header). Use today's UTC date.
- **The "Fun Name" is required** — a short, evocative title (1-4 words, Title
  Case, in straight double quotes) capturing the spirit of the release. Prefer a
  flavorful noun phrase ("The Quiet Reactor", "Glass Houses") over a literal
  restatement ("Add Toggle"). Don't recycle a previous release's name.
- Every entry must include: heading (with fun name), `**Commit summary:**`,
  `**Description:**`, and at least one categorised change list (`### Added`,
  `### Changed`, `### Fixed`, `### Removed`, `### Security`, etc.).
- **Applies if the README carries a version badge:** update the badge in the
  first paragraph of `README.md` to match. *(No README exists yet — if one is
  added with a badge, this gate goes live.)*
- `APP_VERSION_NAME` holds the current release's Fun Name and feeds the in-UI
  version stamp. Bump it every release — it must match the top changelog entry's
  fun name and the git subject.

### Always create the git commit at the end of the change

A version bump that isn't committed isn't actually a release — it's an
uncommitted working-tree edit that disappears on the next `git reset` or context
loss. After finishing the changes for a version bump (code + version + README +
changelog, plus the test required by the test-discipline rule below), `git add`
the affected files and `git commit` them as a single commit. The commit message
should match the convention seen in `git log --oneline` — short subject of the
form `X.Y.Z — "Fun Name" — <one-line summary>`, body optional but encouraged for
non-trivial changes. The fun name in the subject **must match** the fun name in
the changelog entry so a reader scanning `git log` and the changelog side-by-side
sees the same handle on both. Do this even if the user didn't say "please
commit" — the per-commit / per-bump rule already implies a commit happens. If the
change is mid-flight (broken tests, half-written feature) say so and don't bump
the version yet rather than landing an uncommitted bump. **Never run more than
one version bump without committing in between** — if you've bumped to `2.50.0`
and want to also ship `2.50.1`, commit `2.50.0` first, then start the next
change.

### Push every commit immediately after the local commit lands

A commit that only lives on the local machine isn't actually a release — the
remote is the canonical source of truth for collaborators, for CI, and for anyone
scanning the project's history. A backlog of unpushed commits is a coordination
failure: collaborators see a stale tip, CI doesn't run, and a machine crash or
`git reset --hard` loses all of them at once.

```bash
git push origin main
```

Do this for **every** commit, including doc-only bumps: every bump → one commit →
one push. No batching — if the session ends abruptly (context loss, reboot, hook
failure) the unpushed commits are stranded.

If the push fails (network blip, auth, non-fast-forward because someone else
pushed) investigate before retrying. **Never** use `git push --force` to "fix" a
non-fast-forward against a shared branch — fetch first, see what's upstream, and
rebase or merge cleanly. Force-push to a shared branch overwrites collaborators'
work and is one of the few git operations that's genuinely unrecoverable for
them. The user must explicitly authorize force-push for it to happen.

### On MAJOR version bumps, archive the prior changelog

When `APP_VERSION`'s MAJOR segment increments (e.g. `1.x.x` → `2.0.0`):

1. **Rename** `CHANGELOG.md` to `CHANGELOG_v<N>.md` where `<N>` is the
   **outgoing** major version. Keep it at the repo root so it's grep-able next to
   the active changelog.
2. **Create a fresh `CHANGELOG.md`** with the same header preamble, then the new
   `## [X.0.0] - YYYY-MM-DD` entry at the top. No older entries belong in it.
3. **Add a pointer line** just under the header:
   `> For pre-X.0.0 history, see [CHANGELOG_v<N>.md](CHANGELOG_v<N>.md).`
4. The archive is read-only after the rename — never back-patch entries into it.
   A late `1.x.x` fix goes on the active changelog under its own `2.x.y` entry.

---

## Rebuild the running app after every version bump

GameWiki runs as a long-lived Compose container that bakes code at build time —
there is no live reload in the committed configuration.

A commit that bumps `APP_VERSION` does **not** propagate to the running instance
automatically. After committing, rebuild:

```bash
docker compose up -d --build app
```

then poll `GET /health` until it reports the new `APP_VERSION`:

```bash
curl -s http://localhost:8000/health
# {"status":"ok","version":"...","version_name":"...","schema_version":0}
```

This applies to **every** version bump — including doc-only
commits where no source code changed, because the version file itself did and the
endpoint would otherwise report a stale value.

Why this matters:
- Integration tests talk to the **running** app over the network, not to
  in-process code. A new endpoint added in this commit returns **404** until the
  rebuild, so post-bump test runs against a stale process can mask real failures
  or surface spurious ones.
- Manual click-through verification needs the new code running too.
- Migrations run only at process start. A `SCHEMA_VERSION` bump that isn't
  restarted leaves the DB un-migrated even though the code thinks it's applied.

If the rebuild fails (port in use, dependency unhealthy, image build error),
investigate before retrying. **Never reach for destructive workarounds that wipe
persistent volumes or databases** to get past a startup error — that is page
content, and it is not recoverable. Stop the service, fix the root cause, then
re-run the rebuild.

---

## Touch targets must meet Apple's 44×44pt minimum

GameWiki serves a browser UI, so this applies to every template and stylesheet.

All interactive elements (buttons, links, inputs, selects) must have a minimum
tap target of **44×44 px**.

- Never create a button or interactive element with a combined height (padding +
  line-height) below 44 px unless it is inside a deliberately compact panel
  (dense row-based UI — e.g. a page-history or revision list). In those cases use
  a minimum of **32 px** and add a code comment explaining the exception.
- The global `button` rule in the base stylesheet already sets
  `min-height: 44px; display: inline-flex; align-items: center;
  justify-content: center;` — do not remove these.
- The global `input` / `select` rule already sets `min-height: 44px` — do not
  remove it.
- When writing new compact button classes, explicitly set `min-height: 32px`
  (not lower) and do **not** rely on the fallback from the base rule.
- For absolutely-positioned overlay buttons, set `width` and `height` to at least
  44 px, or expand the target area with `padding` so the total touch area is
  44×44 px.
- Avoid `padding: 0`, `padding: 1px`, or `padding: 2px` on any clickable element.

---

## Every new endpoint commit lands an integration test

GameWiki exposes an HTTP surface (page CRUD, search, revisions), so contract
regressions are the main failure mode the suite guards.

The integration test suite is the safety net for contract regressions. **Every
commit that adds an endpoint or changes a message/event payload shape MUST also
land at least one test** for the new surface. Doc-only / refactor-only commits
are exempt.

**The test contract per surface:**

- One happy-path test asserting on (a) status code, (b) the response body shape,
  and (c) any resulting event/broadcast type plus the fields the client actually
  reads.
- At least one error-path test (400 missing fields, 401/403 unauthorized, 404
  unknown resource, or a contract-specific 409 — e.g. an edit conflict on a page
  revision) — pick what's most likely to regress.
- Never hardcode resource IDs. Look pages up through the API by a stable natural
  key (title, slug) so the test survives a reseed.

**Where it lives:** one file per surface, named `tests/<suite>/test_<name>.py`.
Follow the shape of the existing canonical test.

**When the suite can't cover it yet:** if the happy path needs fixture state that
doesn't exist, file the happy-path test as a to-do and ship the **error-path
tests this commit anyway**. Error paths exercise the contract surface without
needing that state.

**CI** (`.github/workflows/ci.yml`) runs automatically on push to `main` and on
every pull request — keep it green. If it is ever switched to
`workflow_dispatch`, say so explicitly here, because it means the branch has
**no automatic regression gate** and someone must fire it by hand.

Two jobs run in parallel:

- **Release metadata** — `scripts/check_release.py` asserts the changelog's top
  entry matches `APP_VERSION`, its Fun Name matches `APP_VERSION_NAME`, and
  `SCHEMA_VERSION` equals the number of migration files. With `--base <ref>` it
  also fails a commit that didn't bump the version. Run it locally before
  committing: `python3 scripts/check_release.py`.
- **Tests and lint** — builds the stack, waits for healthy, asserts the running
  `/health` version matches the source tree, then runs pytest and both ruff
  checks.

**Applies if the project maintains a coverage index:** every test change — add,
remove, rename, or material assertion shift — also updates the coverage doc in
the same commit, including the total-test-count line at the top.

---

## Every doc must be surfaced through the docs index

The docs index is the single discovery surface for every reader-facing document —
operator guides, how-tos, design plans, reference cards, repo-root docs. When you
**create or edit a document** under `docs/` (or the repo-root doc set:
`README.md` / `CHANGELOG.md` / `CLAUDE.md` / `TODO.md` / archived changelogs),
check that the doc is reachable from the index. If it isn't, **add it in the same
commit.**

This rule exists because a doc can otherwise live on disk for many commits before
anyone notices nobody can find it. The fix is structural: tie the index-surfacing
edit to the doc-write commit itself so no doc ever lands invisible.

**In the SAME commit as the doc:**

1. Add the row to the docs index / landing page (grouped by doc type: guides,
   design plans, references, repo documentation).
2. **Applies if docs are served through the app:** add the route/allowlist entry.
3. **Applies if docs are served through the app:** add a per-slug smoke test
   asserting the doc returns 200, contains a recognizable substring from its H1,
   and renders with the nav — plus add the slug to the index-page assertion list
   so a regression that drops the row gets caught.

**Status text for new entries.** Use consistent vocabulary in the index's Status
column — `✅ shipped`, `🟠 partial`, `⚪ proposed`, `⚪ design only` — and update
it as the underlying work moves through phases.

**When NOT to apply.** Files that aren't reader-facing documents: tests, source
code, config, asset files, data/content files. Note the distinction for this
project: **wiki page content is data, not documentation** — pages authored in
GameWiki are never indexed here. Rule of thumb: "would a contributor want to find
this from the docs landing page?" If yes, surface it. If no, skip it. If unsure,
ask.

---

## Offer "what's next" as multiple-choice questions

**Applies if:** always.

When wrapping a commit, presenting candidates for the next piece of work, or
surfacing a list of options, **use the `AskUserQuestion` tool to format the
choices as a multiple-choice menu** rather than embedding the candidates as a
Markdown bullet list at the end of a chat response. A bulleted "candidates
queued" list forces the user to retype their choice in prose; a picker is one
click.

**When to use it:**

- After shipping a version bump, when offering 2–4 follow-up candidates.
- When the user has said "what's next?" and there's more than one reasonable next
  step.
- When picking between implementation approaches and you want explicit guidance.
- Whenever you'd otherwise write "What's next? Candidates queued: ..." or "Say
  the word for any of these: ...".
- Single-option follow-ups that surface the top-priority backlog item — frame it
  as a multi-choice with that item as the recommended option (suffix
  `(Recommended)`) and 1–3 alternatives (lower-priority items, a "different
  scope" tweak, or "plan it first"). The picker gives a 1-click confirm AND a
  redirect path.

**When NOT to use it:**

- Confirmations that don't have alternatives ("Should I commit?" — just commit
  per the per-commit rule).
- Clarifying questions where the option space isn't enumerable (free-form text).
- When the user has already chosen and you're mid-implementation.

**Format:**

- 2–4 options. If you have more than 4 candidates, pick the 3–4 highest-leverage
  ones and mention the rest in the "Other" overflow.
- Lead with the option you'd recommend, suffix its label with `(Recommended)`.
- Use `header` for a short chip label (e.g. `"Next bump"`, `"Approach"`).
- Keep `description` to one short sentence on what that choice triggers.
- One question per call unless the choices are genuinely independent (rare).

**Why this exists.** A trailing prose-bullet list at the bottom of a commit reply
is the anti-pattern — it makes the user do transcription work.

---

## Third-party APIs must be Docker Compose services

GameWiki already uses Docker Compose for local development, so this applies to
every external dependency.

When integrating any external API or data service, add it as a named service in
`docker-compose.yml` rather than calling a public endpoint directly at request
time. This keeps every dependency on the internal Docker network, works offline,
and removes runtime internet calls from the hot path.

**Pattern to follow for every new API:**

1. Add a service block in `docker-compose.yml` with a `healthcheck`.
2. Add the internal base URL as an env var in the `app` service (e.g.
   `MY_API_BASE_URL: http://myapi:port/v1`).
3. Add the env var (commented out) to `.env.example` with a note that
   docker-compose sets it automatically.
4. Read the env var at module level in the relevant module, with a sensible
   public-internet default so the app still works outside Docker:
   ```python
   _MY_API_BASE = os.getenv("MY_API_BASE_URL", "https://api.example.com/v1").rstrip("/")
   ```
5. Use that variable everywhere instead of a hardcoded URL.
