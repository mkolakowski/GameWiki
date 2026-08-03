"""Page data access, shared by the JSON API and the browser UI.

Both surfaces need the same reads and writes but report failure differently —
the API raises HTTPException, the UI re-renders a form. So this layer speaks in
domain errors and leaves the translation to the caller.
"""

import psycopg

from app import markup
from app.db import pool


class PageNotFound(Exception):
    """No page with that slug."""


class RevisionNotFound(Exception):
    """The page exists but has no such revision."""


class SlugTaken(Exception):
    """A page with that slug already exists."""


class UserNotFound(Exception):
    """No user with that id."""


class InvalidRole(Exception):
    """Not one of reader/editor/admin."""


class LastAdminProtected(Exception):
    """Refusing to remove the only admin, which would lock everyone out."""


class RevisionConflict(Exception):
    """The caller edited from a revision that is no longer current."""

    def __init__(self, expected: int, current: int) -> None:
        super().__init__(f"expected revision {expected}, current is {current}")
        self.expected = expected
        self.current = current


def _sync_links(conn, page_id: int, body: str) -> None:
    """Rewrite this page's outgoing links. Callers must be inside a transaction."""
    conn.execute("DELETE FROM page_links WHERE source_id = %s", (page_id,))
    targets = markup.extract_links(body)
    if targets:
        conn.cursor().executemany(
            "INSERT INTO page_links (source_id, target_slug) VALUES (%s, %s)",
            [(page_id, target) for target in sorted(targets)],
        )


RETURNING_USER = "id, issuer, subject, email, name, role"


def upsert_user(
    issuer: str,
    subject: str,
    email: str | None,
    name: str,
    allowed: bool,
    is_admin: bool = False,
) -> dict:
    """Record the signed-in identity, keyed on (issuer, subject).

    Email and name are refreshed on every sign-in, since the provider is the
    authority on both and either can change.

    The role is recomputed from `allowed` on every sign-in so that removing
    someone from the allowlist actually revokes their access. Three exceptions:
    an address in ADMIN_EMAILS is always admin, the very first account on a
    fresh instance becomes admin so there is someone to administer it, and an
    existing admin is never demoted — an operator shouldn't be able to lock
    themselves out by editing an env var.
    """
    with pool.connection() as conn, conn.transaction():
        existing = conn.execute(
            "SELECT id, role, role_source FROM users WHERE issuer = %s AND subject = %s FOR UPDATE",
            (issuer, subject),
        ).fetchone()

        if existing is None:
            first_ever = conn.execute("SELECT count(*) AS n FROM users").fetchone()["n"] == 0
            if is_admin or first_ever:
                role = "admin"
            else:
                role = "editor" if allowed else "reader"
            return conn.execute(
                "INSERT INTO users (issuer, subject, email, name, role)"
                f" VALUES (%s, %s, %s, %s, %s) RETURNING {RETURNING_USER}",
                (issuer, subject, email, name, role),
            ).fetchone()

        if is_admin or existing["role"] == "admin":
            role = "admin"
        elif existing["role_source"] == "manual":
            # An admin set this deliberately; the allowlist doesn't override it.
            role = existing["role"]
        else:
            role = "editor" if allowed else "reader"
        return conn.execute(
            "UPDATE users SET email = %s, name = %s, role = %s, last_seen_at = now()"
            f" WHERE id = %s RETURNING {RETURNING_USER}",
            (email, name, role, existing["id"]),
        ).fetchone()


def get_user(user_id: int) -> dict | None:
    """The current state of an account, or None if it no longer exists.

    Read on every authenticated request so authorization decisions use the
    role as it is now rather than as it was at sign-in.
    """
    with pool.connection() as conn:
        return conn.execute(
            f"SELECT {RETURNING_USER} FROM users WHERE id = %s", (user_id,)
        ).fetchone()


ROLES = ("reader", "editor", "admin")


def list_users() -> list[dict]:
    """Every account, admins first then alphabetical."""
    with pool.connection() as conn:
        return conn.execute(
            "SELECT id, name, email, role, created_at, last_seen_at FROM users"
            " ORDER BY CASE role WHEN 'admin' THEN 0 WHEN 'editor' THEN 1 ELSE 2 END,"
            " lower(name), id"
        ).fetchall()


def set_user_role(target_id: int, new_role: str, actor: dict) -> dict:
    """Change a role and record who did it.

    Refuses to remove the last admin — an instance with no admin can never
    hand out the role again without database access.
    """
    if new_role not in ROLES:
        raise InvalidRole(new_role)

    with pool.connection() as conn, conn.transaction():
        target = conn.execute(
            "SELECT id, name, email, role FROM users WHERE id = %s FOR UPDATE", (target_id,)
        ).fetchone()
        if target is None:
            raise UserNotFound(target_id)

        old_role = target["role"]
        if old_role == new_role:
            return target

        if old_role == "admin":
            admins = conn.execute(
                "SELECT count(*) AS n FROM users WHERE role = 'admin'"
            ).fetchone()["n"]
            if admins <= 1:
                raise LastAdminProtected(target_id)

        updated = conn.execute(
            "UPDATE users SET role = %s, role_source = 'manual' WHERE id = %s"
            f" RETURNING {RETURNING_USER}",
            (new_role, target_id),
        ).fetchone()

        conn.execute(
            "INSERT INTO role_changes"
            " (target_id, actor_id, target_label, actor_label, old_role, new_role)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (
                target_id,
                actor.get("id"),
                target["email"] or target["name"],
                actor.get("email") or actor.get("name") or "unknown",
                old_role,
                new_role,
            ),
        )

    return updated


def recent_role_changes(limit: int = 20) -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT target_label, actor_label, old_role, new_role, changed_at"
            " FROM role_changes ORDER BY changed_at DESC, id DESC LIMIT %s",
            (limit,),
        ).fetchall()


def existing_slugs(slugs: set[str]) -> set[str]:
    """Which of these slugs actually have a page — drives red-link styling."""
    if not slugs:
        return set()

    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT slug FROM pages WHERE slug = ANY(%s)", (sorted(slugs),)
        ).fetchall()

    return {row["slug"] for row in rows}


def backlinks(slug: str) -> list[dict]:
    """Pages linking here — "what links here". Self-links are excluded."""
    with pool.connection() as conn:
        return conn.execute(
            "SELECT p.slug, p.title FROM page_links l"
            " JOIN pages p ON p.id = l.source_id"
            " WHERE l.target_slug = %s AND p.slug <> %s"
            " ORDER BY p.title",
            (slug, slug),
        ).fetchall()


def list_pages() -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT slug, title, revision, updated_at FROM pages ORDER BY title"
        ).fetchall()


SEARCH_LIMIT = 50

# ts_headline options. The sentinels are the ones markup.highlight_snippet
# swaps for <mark> after escaping — see the note there on why they aren't
# `<mark>` already.
_HEADLINE_OPTS = (
    f"StartSel={markup.HL_START}, StopSel={markup.HL_STOP},"
    " MaxWords=24, MinWords=8, MaxFragments=2, FragmentDelimiter= … "
)


def search_pages(query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    """Rank pages against a user-typed query.

    `websearch_to_tsquery` is what makes this safe to point at raw input: it
    accepts quoted phrases, `or`, and `-exclusion`, and it degrades punctuation
    soup to an empty query rather than raising the way `to_tsquery` would. An
    empty query matches nothing, so a search for `&&&` is zero results and not
    a 500.

    A query that is only stop words ("the", "a") is likewise empty and finds
    nothing, which is the standard full-text tradeoff rather than a bug.
    """
    if not query.strip():
        return []

    with pool.connection() as conn:
        return conn.execute(
            "WITH q AS (SELECT websearch_to_tsquery('english', %s) AS query)"
            " SELECT p.slug, p.title, p.revision, p.updated_at,"
            "        ts_headline('english', p.body, q.query, %s) AS snippet,"
            "        ts_rank_cd(p.search_vector, q.query) AS rank"
            " FROM pages p, q"
            " WHERE p.search_vector @@ q.query"
            " ORDER BY rank DESC, p.title LIMIT %s",
            (query, _HEADLINE_OPTS, limit),
        ).fetchall()


def get_page(slug: str) -> dict:
    with pool.connection() as conn:
        page = conn.execute(
            "SELECT slug, title, body, revision, updated_at FROM pages WHERE slug = %s",
            (slug,),
        ).fetchone()

    if page is None:
        raise PageNotFound(slug)
    return page


def create_page(slug: str, title: str, body: str, author_id: int | None = None) -> dict:
    with pool.connection() as conn:
        try:
            with conn.transaction():
                page = conn.execute(
                    "INSERT INTO pages (slug, title, body) VALUES (%s, %s, %s)"
                    " RETURNING id, slug, title, body, revision, updated_at",
                    (slug, title, body),
                ).fetchone()
                # The initial content is revision 1 — history starts at creation,
                # not at the first edit.
                conn.execute(
                    "INSERT INTO page_revisions"
                    " (page_id, revision, title, body, created_at, author_id)"
                    " VALUES (%s, 1, %s, %s, %s, %s)",
                    (page["id"], page["title"], page["body"], page["updated_at"], author_id),
                )
                _sync_links(conn, page["id"], page["body"])
        except psycopg.errors.UniqueViolation:
            raise SlugTaken(slug) from None

    return page


def update_page(
    slug: str,
    title: str,
    body: str,
    expected_revision: int | None = None,
    author_id: int | None = None,
) -> dict:
    """Replace a page's content, appending a revision.

    When expected_revision is given it must be the current one, otherwise
    RevisionConflict is raised and nothing is written.
    """
    with pool.connection() as conn, conn.transaction():
        # FOR UPDATE holds the row until commit, so the check-then-write below
        # can't interleave with a concurrent edit.
        current = conn.execute(
            "SELECT id, revision FROM pages WHERE slug = %s FOR UPDATE", (slug,)
        ).fetchone()

        if current is None:
            raise PageNotFound(slug)

        if expected_revision is not None and expected_revision != current["revision"]:
            raise RevisionConflict(expected_revision, current["revision"])

        page = conn.execute(
            "UPDATE pages SET title = %s, body = %s, revision = revision + 1,"
            " updated_at = now() WHERE id = %s"
            " RETURNING slug, title, body, revision, updated_at",
            (title, body, current["id"]),
        ).fetchone()

        conn.execute(
            "INSERT INTO page_revisions"
            " (page_id, revision, title, body, created_at, author_id)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (
                current["id"],
                page["revision"],
                page["title"],
                page["body"],
                page["updated_at"],
                author_id,
            ),
        )
        _sync_links(conn, current["id"], page["body"])

    return page


def list_revisions(slug: str) -> list[dict]:
    """Newest revision first."""
    with pool.connection() as conn:
        page = conn.execute("SELECT id FROM pages WHERE slug = %s", (slug,)).fetchone()
        if page is None:
            raise PageNotFound(slug)

        # Revisions written before authorship existed have no author; the view
        # renders those as "unknown" rather than hiding them.
        return conn.execute(
            "SELECT r.revision, r.title, r.created_at, u.name AS author"
            " FROM page_revisions r LEFT JOIN users u ON u.id = r.author_id"
            " WHERE r.page_id = %s ORDER BY r.revision DESC",
            (page["id"],),
        ).fetchall()


def get_revision(slug: str, revision: int) -> dict:
    with pool.connection() as conn:
        page = conn.execute("SELECT id FROM pages WHERE slug = %s", (slug,)).fetchone()
        if page is None:
            raise PageNotFound(slug)

        row = conn.execute(
            "SELECT r.revision, r.title, r.body, r.created_at, u.name AS author"
            " FROM page_revisions r LEFT JOIN users u ON u.id = r.author_id"
            " WHERE r.page_id = %s AND r.revision = %s",
            (page["id"], revision),
        ).fetchone()

    if row is None:
        raise RevisionNotFound(revision)
    return row
