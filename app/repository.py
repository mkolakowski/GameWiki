"""Page data access, shared by the JSON API and the browser UI.

Both surfaces need the same reads and writes but report failure differently —
the API raises HTTPException, the UI re-renders a form. So this layer speaks in
domain errors and leaves the translation to the caller.
"""

import psycopg

from app.db import pool


class PageNotFound(Exception):
    """No page with that slug."""


class RevisionNotFound(Exception):
    """The page exists but has no such revision."""


class SlugTaken(Exception):
    """A page with that slug already exists."""


class RevisionConflict(Exception):
    """The caller edited from a revision that is no longer current."""

    def __init__(self, expected: int, current: int) -> None:
        super().__init__(f"expected revision {expected}, current is {current}")
        self.expected = expected
        self.current = current


def list_pages() -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT slug, title, revision, updated_at FROM pages ORDER BY title"
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


def create_page(slug: str, title: str, body: str) -> dict:
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
                    "INSERT INTO page_revisions (page_id, revision, title, body, created_at)"
                    " VALUES (%s, 1, %s, %s, %s)",
                    (page["id"], page["title"], page["body"], page["updated_at"]),
                )
        except psycopg.errors.UniqueViolation:
            raise SlugTaken(slug) from None

    return page


def update_page(slug: str, title: str, body: str, expected_revision: int | None = None) -> dict:
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
            "INSERT INTO page_revisions (page_id, revision, title, body, created_at)"
            " VALUES (%s, %s, %s, %s, %s)",
            (current["id"], page["revision"], page["title"], page["body"], page["updated_at"]),
        )

    return page


def list_revisions(slug: str) -> list[dict]:
    """Newest revision first."""
    with pool.connection() as conn:
        page = conn.execute("SELECT id FROM pages WHERE slug = %s", (slug,)).fetchone()
        if page is None:
            raise PageNotFound(slug)

        return conn.execute(
            "SELECT revision, title, created_at FROM page_revisions"
            " WHERE page_id = %s ORDER BY revision DESC",
            (page["id"],),
        ).fetchall()


def get_revision(slug: str, revision: int) -> dict:
    with pool.connection() as conn:
        page = conn.execute("SELECT id FROM pages WHERE slug = %s", (slug,)).fetchone()
        if page is None:
            raise PageNotFound(slug)

        row = conn.execute(
            "SELECT revision, title, body, created_at FROM page_revisions"
            " WHERE page_id = %s AND revision = %s",
            (page["id"], revision),
        ).fetchone()

    if row is None:
        raise RevisionNotFound(revision)
    return row
