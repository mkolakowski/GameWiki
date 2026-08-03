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

## [0.9.0] - 2026-08-03 — "The Key Ring"

**Commit summary:** add the admin accounts screen, an `ADMIN_EMAILS` bootstrap,
and an audit trail for role changes.

**Description:** 0.8.0 introduced the admin role but nothing to do with it —
changing anyone's role meant `UPDATE users SET role = ...` by hand. `/admin/users`
now lists every account with its last-seen time and role, and changes roles from
the browser. Every change is recorded. `SCHEMA_VERSION` goes to `6`.

**Admins are now bootstrapped deliberately.** `ADMIN_EMAILS` names accounts that
are always admin. The old rule — first account on a fresh instance becomes
admin — remains as a fallback, but on a public instance that could be a
passer-by, so an explicit list is the better answer. It also made the admin
tests deterministic: "who is admin" no longer depends on who signed in first.

Two guards, both in the repository layer so any future caller inherits them:

- **The last admin can't be demoted.** An instance with no admin can never hand
  the role back out without database access.
- **Self-demotion needs explicit confirmation** — a tick box on your own row.
  Losing your own admin rights shouldn't be one careless click. The actor's
  session is updated in place afterwards, so they aren't left holding a stale
  admin cookie.

### Fixed a design flaw the tests exposed

The first version of this screen was **nearly useless**, and the test suite
caught it: a manual promotion was silently undone at the promoted person's next
sign-in, because 0.8.0 recomputes the role from the allowlist on every sign-in.
Since anyone on the allowlist is already an editor, the screen could only ever
demote people.

`users.role_source` now distinguishes `allowlist` from `manual`. Allowlist-derived
roles keep tracking `ALLOWED_EMAILS`/`ALLOWED_DOMAINS`, so removing someone still
revokes access — the property 0.8.0 was built for. Roles an admin set explicitly
are left alone. This was folded into migration 006 rather than added as a 007,
since 006 was unreleased; the local development database was patched by hand to
match, and the whole migration chain was then replayed against a virgin database
to confirm it applies cleanly from scratch.

Verified end to end: six migrations apply to an empty database with
`SCHEMA_VERSION` matching, `/health` reports `0.9.0` / `schema_version: 6`,
`pytest -q` passes 119 tests (up from 105), ruff clean.

### Added

- `app/admin.py` — `GET /admin/users` and `POST /admin/users/{id}/role`,
  admin-only.
- `app/templates/admin_users.html` — accounts table with a per-row role select,
  a confirm box on your own row, and the recent role-change log.
- `app/migrations/006_create_role_changes.sql` — the `role_changes` audit table
  and `users.role_source`. Actor and target labels are denormalised alongside
  the foreign keys so an audit record stays readable after an account is
  deleted.
- `ADMIN_EMAILS` config and `require_admin()`.
- `repo.list_users`, `repo.set_user_role`, `repo.recent_role_changes`, and the
  `UserNotFound` / `InvalidRole` / `LastAdminProtected` errors.
- An Accounts link in the nav, shown only to admins.
- `tests/api/test_admin.py` — 14 tests: access control for editor, reader, and
  anonymous; promotion and its effect at next sign-in; unknown account and
  invalid role; both guards; the audit record naming who did what; and a
  hostile display name escaped in the table and the log.

### Changed

- `app/version.py`: `APP_VERSION` `0.8.0` → `0.9.0`, `APP_VERSION_NAME` →
  `"The Key Ring"`, `SCHEMA_VERSION` `5` → `6`.
- `repo.upsert_user` takes `is_admin` and respects `role_source`.

### Known gaps

- **Role changes still take effect at next sign-in** for everyone except the
  admin making the change, because the role is snapshotted into the session. A
  demoted user keeps their access until their session ends. Checking the role
  per request would fix it at the cost of a query per write.
- No way to delete an account or revoke a live session from the screen.
- Still no CSRF tokens, and still unverified against real Google.

---

## [0.8.0] - 2026-08-03 — "The Guest List"

**Commit summary:** add an edit allowlist and user roles, so authentication
finally decides something.

**Description:** 0.7.0 established *who* you are; this decides *whether you may
write*. Until now any Google account on earth could edit any page. Roles are
`reader`, `editor`, and `admin`, and `SCHEMA_VERSION` goes to `5`.

`ALLOWED_EMAILS` and `ALLOWED_DOMAINS` are comma-separated env lists. Matching
either earns the editor role at sign-in; everyone else signs in as a reader and
gets a 403 on any write while keeping full read access.

**The role is recomputed on every sign-in**, not stored once, so taking someone
off the allowlist actually revokes their access rather than grandfathering
them. Two exceptions: the first account on a fresh instance becomes admin so
there is someone to administer it, and an existing admin is never automatically
demoted — an operator shouldn't be able to lock themselves out by editing an
env var. Migration 005 promotes the earliest existing account, so an instance
upgrading from 0.7.0 doesn't end up with no admin at all.

**With both lists unset, the wiki stays open to any account that can sign
in** — the 0.7.0 behaviour, kept so an upgrade doesn't lock out every existing
editor. That is a permissive default, so `/health` reports
`allowlist_configured` and it's documented in `.env.example` rather than being
silent.

**401 and 403 are answered differently on purpose.** 401 means "we don't know
who you are" and sends a browser to sign in. 403 means "we know exactly who you
are and the answer is no" — signing in again would achieve nothing, so readers
get a page saying so, naming the account they're signed in as and explaining
that an operator has to add them. Readers also stop seeing Edit and New page
affordances that would only fail.

Verified end to end: migration 005 applied, `/health` reports `0.8.0` /
`schema_version: 5` / `allowlist_configured: true`, `pytest -q` passes 105
tests (up from 92), ruff clean. Probed by hand: an allowlisted email and an
allowlisted domain both write successfully, a non-allowlisted account gets 403
on the API and the explanatory page in a browser while still reading fine, and
the database shows the expected admin/editor/reader split.

### Added

- `app/migrations/005_add_user_roles.sql` — `users.role` with a CHECK
  constraint, defaulting to `reader`, plus promotion of the earliest existing
  account to admin.
- `ALLOWED_EMAILS` / `ALLOWED_DOMAINS` config, `allowlist_is_configured()`, and
  `email_is_allowed()`.
- `require_editor()` alongside `require_user()`, now used on every write path
  on both the JSON and HTML surfaces.
- `app/templates/forbidden.html` — the 403 page, rendered for browsers by the
  exception handler in `app/main.py`.
- `allowlist_configured` on `/health`.
- `tests/api/test_authz.py` — 13 tests: allowlist by email and by domain,
  outsiders blocked on create, update, and the edit form, outsiders still able
  to read, the HTML-vs-JSON refusal split, edit affordances hidden from
  readers, re-evaluation of a role when an address moves onto the allowlist,
  and no silent promotion from repeated sign-ins.

### Changed

- `app/version.py`: `APP_VERSION` `0.7.0` → `0.8.0`, `APP_VERSION_NAME` →
  `"The Guest List"`, `SCHEMA_VERSION` `4` → `5`.
- **Breaking where an allowlist is set:** accounts outside it now get 403 on
  writes that previously succeeded.
- `repo.upsert_user` takes an `allowed` flag and returns the role; the session
  carries it.
- `/health` gained `allowlist_configured` — clients asserting an exact key set
  need updating.
- Nav hides New page from readers and shows the role in the user tooltip.

### Known gaps

- **No admin UI.** Admin currently means "editor who can't be demoted by an
  allowlist change". Changing anyone's role is a manual
  `UPDATE users SET role = ...`. An admin screen is the natural next bump.
- **Role changes take effect at next sign-in**, since the role is snapshotted
  into the session. A demoted user keeps editing until their session ends.
- Still no CSRF tokens — see the gap noted in 0.7.0.
- Still unverified against real Google.

---

## [0.7.0] - 2026-08-03 — "Who Goes There"

**Commit summary:** add Google OIDC sign-in, gate writes on a session, and
attribute each revision to its author.

**Description:** Closes the last structural hole: until now anyone who could
reach the app could rewrite any page anonymously. Reads stay public; **writes
require a signed-in user**, and every revision records who wrote it.
`SCHEMA_VERSION` goes to `4`.

Identity comes from an OIDC provider, so the app never sees or stores a
credential — there is no password column. Users are keyed on
`(issuer, subject)`, not email, because `sub` is only unique within an issuer
and a Google account can change its address. Display name and email are
refreshed from the provider on every sign-in.

**The app is provider-agnostic and defaults to Google.** `OIDC_DISCOVERY_URL`
is read from the environment and falls back to Google's discovery document, so
production needs only a client ID and secret. See `.env.example` for the Google
Cloud console setup.

**Testing it required a provider on the internal network.** The suite talks to
the running container over HTTP, so it can't monkeypatch an auth bypass, and CI
can't reach Google. CLAUDE.md's Compose rule points at the answer:
`devtools/fake_oidc.py` runs as the `oidc` service and speaks real OIDC —
discovery, JWKS, code exchange, RS256-signed id_token — so the app runs its
genuine Authlib path. It approves every request without asking anyone anything,
which is exactly what a test provider should do, and it must never be deployed.
**What this cannot prove is that sign-in works against Google**: the stub is
deliberately permissive, so a check Google enforces and the app skips would go
unnoticed. Real-Google verification is manual and has not been done.

### Fixed a real bug found by accident

Recreating the `oidc` container mid-session produced a **500 on every
sign-in**: `BadSignatureError`. Authlib caches the provider's JWK set on the
client and never expires it, so once the signing key changed, no id_token would
verify again until the process restarted.

This is not a stub artifact — **Google rotates its signing keys routinely**, so
the same wedge would eventually hit production. The authorization code is
already spent by the time verification fails, so the failing attempt can't be
salvaged; the callback now catches the JOSE error, force-refreshes the key set
so the *next* attempt succeeds, and shows a retry link instead of a traceback.
Verified by hand: after a rotation, attempt 1 returns a clean 400 and attempt 2
signs in.

### Added

- `app/auth.py` — `/auth/login`, `/auth/callback`, `/auth/logout`, plus
  `current_user` and `require_user`. `?next=` is restricted to same-site paths
  so a crafted link can't bounce a signed-in user to another origin.
- `app/migrations/004_create_users.sql` — `users` (unique on
  `(issuer, subject)`) and a nullable `page_revisions.author_id` with
  `ON DELETE SET NULL`, so deleting a user never deletes wiki history.
  Revisions written before this migration show as "unknown".
- Session cookie via Starlette `SessionMiddleware`, `SameSite=Lax`, and
  `Secure` when `SESSION_HTTPS_ONLY` is set.
- `devtools/fake_oidc.py` and the `oidc` Compose service, with
  `/_test/identity` to choose who signs in and `/_test/rotate_key` to simulate
  a key rotation.
- Author shown in the history list, on the revision view, and returned as
  `author` on both revision API shapes.
- Nav shows the signed-in user with a Sign out link, or Sign in with Google.
  Edit and New page become sign-in prompts when anonymous.
- A browser hitting a write path gets a 303 to sign-in; an API client gets a
  JSON 401. A raw 401 is a dead end for someone who just clicked Edit, but
  redirecting an API client to an HTML page would be worse.
- `auth_configured` on `/health`.
- `tests/api/test_auth.py` — 18 tests: the write gate on both surfaces,
  anonymous reads still working, redirect-vs-JSON behaviour, sign-out,
  same-site `next` enforcement, per-revision authorship across two users,
  identity stability when a display name changes, a hostile display name
  escaped in the history and nav, and recovery from a key rotation.
- Dependencies: `authlib`, `itsdangerous`; `httpx` moved to a runtime dep.

### Changed

- `app/version.py`: `APP_VERSION` `0.6.0` → `0.7.0`, `APP_VERSION_NAME` →
  `"Who Goes There"`, `SCHEMA_VERSION` `3` → `4`.
- **Breaking for API clients:** `POST /pages` and `PUT /pages/{slug}` now
  return **401** without a session. Anonymous scripts against this API stop
  working.
- Response shapes gained fields: `/health` has `auth_configured`, and both
  revision shapes have `author`. Clients asserting exact key sets need
  updating.
- `GET /pages/{slug}/revisions/{n}` now actually reports its author — the query
  wasn't joining `users`, so it returned `null` even for authored revisions.
- The rebuild command is now `docker compose up -d --build` (three services).
  Updated in CLAUDE.md and CI.
- `CLAUDE.md`: the Compose-services rule gained an identity-provider exception
  describing this shape.

### Known gaps

- **CSRF relies on `SameSite=Lax` alone** — there are no CSRF tokens on the
  edit forms. Lax keeps the session cookie off cross-site POSTs, which covers
  the common case, but a token is the belt-and-braces answer.
- **No authorization, only authentication.** Any signed-in Google account can
  edit any page. There are no roles, no allowlist, and no page protection.
- Sign-out clears the local session only; the Google session is untouched.
- Sessions are unsigned-out by a restart unless `SESSION_SECRET` is set.
- Manual browser sign-in against the stub needs `127.0.0.1 oidc` in
  `/etc/hosts`, since the authorize URL uses the internal Compose hostname.

---

## [0.6.0] - 2026-08-03 — "The Red Thread"

**Commit summary:** render page bodies as markdown, resolve `[[wiki links]]`
between pages, and show backlinks.

**Description:** Pages can point at each other, which is what makes a wiki a
wiki rather than a pile of documents. Bodies render as markdown;
`[[Page Title]]` resolves to a link, and `[[Page Title|other words]]` changes
the link text. `SCHEMA_VERSION` goes to `3`.

A link to a page that doesn't exist becomes a **red link** pointing at the
create form with the slug and title prefilled — the wiki convention where a
missing link doubles as an invitation to write the page. It turns blue on its
own the moment someone creates the target, because `page_links.target_slug` is
deliberately not a foreign key. Each page also lists **what links here**,
maintained in the same transaction as the write, so removing a link from a body
removes the backlink.

**Security is the whole risk surface of this bump**, since bodies are
user-authored and now reach the browser as HTML. Three layers: markdown-it runs
with `html=False` so raw HTML is escaped rather than passed through; its link
validator rejects `javascript:`, `vbscript:`, and `data:` destinations; and the
result goes through nh3 (ammonia) against a safe allowlist. Wiki-link display
text is escaped before being spliced into markdown source so a crafted label
can't break out of the link syntax.

**The escaping tests were rewritten mid-implementation.** The first versions
asserted with substring checks, and seven failed — every one a false alarm: the
payloads were being correctly escaped, and the assertions couldn't tell
`<script>` from `&lt;script&gt;`, nor did they expect the
`rel="noopener noreferrer"` nh3 adds. A substring check is the wrong tool here;
it fails on safely-escaped text and passes on markup smuggled inside an
attribute. They now parse the HTML and assert structurally — no dangerous
element, no `on*` handler, no dangerous URL scheme — via an `assert_safe_html`
fixture. That auditor was itself checked against five known-bad inputs
including a tab-obfuscated `java\tscript:` URL, so it can actually fail.

Verified end to end: migration 003 applied and backfilled the link graph for
pre-existing pages, `/health` reports `0.6.0` / "The Red Thread" /
`schema_version: 3`, `pytest -q` passes 74 tests (up from 34), ruff clean, and
the create → red link → target created → link resolves → backlink appears loop
walked by hand. **Still not seen in a real browser** — none available here — so
the markdown and red-link styling is asserted in CSS and tests, not looked at.

### Added

- `app/markup.py` — `slugify`, `extract_links`, `resolve_wiki_links`, and
  `render`, with the sanitising pipeline described above.
- `app/migrations/003_create_page_links.sql` — `page_links` (`source_id` FK
  cascade, `target_slug`, indexed on target) plus a SQL backfill of the graph
  for existing pages.
- Backlinks section on the page view, omitted when there are none. Self-links
  are excluded.
- `GET /new` now accepts `slug` and `title` query params, so red links arrive
  prefilled.
- Markdown styling in `base.css` — headings, code, `pre`, blockquotes, tables —
  and red links styled by href prefix (`a[href^="/new?"]`), which avoids putting
  raw HTML through the markdown pipeline just to carry a CSS class.
- `tests/unit/test_markup.py` — 22 tests: slugify cases, link extraction,
  resolution, and 13 hostile bodies asserted structurally.
- `tests/api/test_links.py` — 12 tests through the running app: red links, link
  resolution after target creation, backlink add and removal, markdown
  rendering, and stored-XSS checks on the page, index, history, and prefilled
  form.
- `assert_safe_html` fixture and `audit_html` helper in `tests/conftest.py`.
- Dependencies: `markdown-it-py`, `nh3`.

### Changed

- `app/version.py`: `APP_VERSION` `0.5.1` → `0.6.0`, `APP_VERSION_NAME` →
  `"The Red Thread"`, `SCHEMA_VERSION` `2` → `3`.
- `app/repository.py`: writes sync the link graph in the same transaction; adds
  `existing_slugs` and `backlinks`.
- Page bodies are markdown rather than preformatted plain text. **Existing
  bodies re-render** — leading `#`, `*`, or `_` that used to be literal now has
  meaning, and single newlines no longer force a line break.
- Edit and create forms document the `[[link]]` syntax.

### Known gaps

- `markup.slugify` is reimplemented in SQL in migration 003 for the backfill.
  That copy is frozen; changing the Python rules needs a new migration, not an
  edit to 003.
- Non-ASCII link text is dropped rather than transliterated, so `[[Pokémon]]`
  targets `pok-mon`.
- No search, no authentication.

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
