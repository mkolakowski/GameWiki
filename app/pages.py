"""Wiki page CRUD and revision history.

Pages are addressed by `slug` — the stable natural key. The surrogate `id`
column is never exposed through the API, so clients and tests survive a reseed.

Every version of a page is recorded in `page_revisions`, including the original,
so a `PUT` never destroys the prior text. `pages.revision` points at the latest
one and is served as the ETag.
"""

from datetime import datetime

import psycopg
from fastapi import APIRouter, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.db import pool

router = APIRouter(prefix="/pages", tags=["pages"])

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class PageCreate(BaseModel):
    slug: str = Field(pattern=SLUG_PATTERN, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    body: str = ""


class PageUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = ""


class PageSummary(BaseModel):
    slug: str
    title: str
    revision: int
    updated_at: datetime


class Page(PageSummary):
    body: str


class RevisionSummary(BaseModel):
    revision: int
    title: str
    created_at: datetime


class Revision(RevisionSummary):
    body: str


def _parse_if_match(if_match: str) -> int:
    """Read a revision number out of an If-Match header.

    Accepts `"3"`, `W/"3"`, and a bare `3`. Anything else is a malformed
    request rather than a conflict.
    """
    candidate = if_match.strip().removeprefix("W/").strip().strip('"')
    if not candidate.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"malformed If-Match {if_match!r}: expected a revision number",
        )
    return int(candidate)


def _etag(response: Response, revision: int) -> None:
    response.headers["ETag"] = f'"{revision}"'


@router.get("", response_model=list[PageSummary])
def list_pages() -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(
            "SELECT slug, title, revision, updated_at FROM pages ORDER BY title"
        ).fetchall()


@router.post("", response_model=Page, status_code=status.HTTP_201_CREATED)
def create_page(payload: PageCreate, response: Response) -> dict:
    with pool.connection() as conn:
        try:
            with conn.transaction():
                page = conn.execute(
                    "INSERT INTO pages (slug, title, body) VALUES (%s, %s, %s)"
                    " RETURNING id, slug, title, body, revision, updated_at",
                    (payload.slug, payload.title, payload.body),
                ).fetchone()
                # The initial content is revision 1 — history starts at creation,
                # not at the first edit.
                conn.execute(
                    "INSERT INTO page_revisions (page_id, revision, title, body, created_at)"
                    " VALUES (%s, 1, %s, %s, %s)",
                    (page["id"], page["title"], page["body"], page["updated_at"]),
                )
        except psycopg.errors.UniqueViolation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"a page with slug {payload.slug!r} already exists",
            ) from None

    _etag(response, page["revision"])
    return page


@router.get("/{slug}", response_model=Page)
def get_page(slug: str, response: Response) -> dict:
    with pool.connection() as conn:
        page = conn.execute(
            "SELECT slug, title, body, revision, updated_at FROM pages WHERE slug = %s",
            (slug,),
        ).fetchone()

    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such page")

    _etag(response, page["revision"])
    return page


@router.put("/{slug}", response_model=Page)
def update_page(
    slug: str,
    payload: PageUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict:
    """Replace a page's content, appending a revision.

    If-Match is optional. When supplied it must name the revision the client
    read, otherwise the edit is rejected as a conflict — this is how two
    editors racing on the same page avoid silently clobbering each other.
    """
    expected = _parse_if_match(if_match) if if_match is not None else None

    with pool.connection() as conn, conn.transaction():
        # FOR UPDATE holds the row until commit, so the check-then-write below
        # can't interleave with a concurrent PUT.
        current = conn.execute(
            "SELECT id, revision FROM pages WHERE slug = %s FOR UPDATE", (slug,)
        ).fetchone()

        if current is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such page")

        if expected is not None and expected != current["revision"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"page has moved on: If-Match named revision {expected} but the "
                    f"current revision is {current['revision']}"
                ),
            )

        page = conn.execute(
            "UPDATE pages SET title = %s, body = %s, revision = revision + 1,"
            " updated_at = now() WHERE id = %s"
            " RETURNING slug, title, body, revision, updated_at",
            (payload.title, payload.body, current["id"]),
        ).fetchone()

        conn.execute(
            "INSERT INTO page_revisions (page_id, revision, title, body, created_at)"
            " VALUES (%s, %s, %s, %s, %s)",
            (current["id"], page["revision"], page["title"], page["body"], page["updated_at"]),
        )

    _etag(response, page["revision"])
    return page


@router.get("/{slug}/revisions", response_model=list[RevisionSummary])
def list_revisions(slug: str) -> list[dict]:
    """Newest revision first."""
    with pool.connection() as conn:
        page = conn.execute("SELECT id FROM pages WHERE slug = %s", (slug,)).fetchone()
        if page is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such page")

        return conn.execute(
            "SELECT revision, title, created_at FROM page_revisions"
            " WHERE page_id = %s ORDER BY revision DESC",
            (page["id"],),
        ).fetchall()


@router.get("/{slug}/revisions/{revision}", response_model=Revision)
def get_revision(slug: str, revision: int) -> dict:
    with pool.connection() as conn:
        page = conn.execute("SELECT id FROM pages WHERE slug = %s", (slug,)).fetchone()
        if page is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such page")

        row = conn.execute(
            "SELECT revision, title, body, created_at FROM page_revisions"
            " WHERE page_id = %s AND revision = %s",
            (page["id"], revision),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such revision")
    return row
