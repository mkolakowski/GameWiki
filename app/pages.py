"""Wiki page CRUD and revision history — the JSON API.

Pages are addressed by `slug` — the stable natural key. The surrogate `id`
column is never exposed through the API, so clients and tests survive a reseed.

Reads and writes live in `app.repository`; this module is the HTTP contract
over them — status codes, response shapes, and ETags.
"""

from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app import repository as repo
from app.auth import require_editor

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
    author: str | None = None


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


_NO_PAGE = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such page")


@router.get("", response_model=list[PageSummary])
def list_pages(q: str = "") -> list[dict]:
    """Every page by title, or the matches for `q` ranked best-first.

    Search lives here rather than at `/pages/search` on purpose: that path
    would shadow a page whose slug happens to be `search`, and the shape being
    returned is a page list either way. The ranked snippet is a presentation
    concern and stays on the HTML surface at `/search`.
    """
    if q.strip():
        return repo.search_pages(q)
    return repo.list_pages()


@router.post("", response_model=Page, status_code=status.HTTP_201_CREATED)
def create_page(payload: PageCreate, request: Request, response: Response) -> dict:
    author = require_editor(request)
    try:
        page = repo.create_page(payload.slug, payload.title, payload.body, author["id"])
    except repo.SlugTaken:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"a page with slug {payload.slug!r} already exists",
        ) from None

    _etag(response, page["revision"])
    return page


@router.get("/{slug}", response_model=Page)
def get_page(slug: str, response: Response) -> dict:
    try:
        page = repo.get_page(slug)
    except repo.PageNotFound:
        raise _NO_PAGE from None

    _etag(response, page["revision"])
    return page


@router.put("/{slug}", response_model=Page)
def update_page(
    slug: str,
    payload: PageUpdate,
    request: Request,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict:
    """Replace a page's content, appending a revision.

    If-Match is optional. When supplied it must name the revision the client
    read, otherwise the edit is rejected as a conflict — this is how two
    editors racing on the same page avoid silently clobbering each other.
    """
    author = require_editor(request)
    expected = _parse_if_match(if_match) if if_match is not None else None

    try:
        page = repo.update_page(slug, payload.title, payload.body, expected, author["id"])
    except repo.PageNotFound:
        raise _NO_PAGE from None
    except repo.RevisionConflict as conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"page has moved on: If-Match named revision {conflict.expected} but the "
                f"current revision is {conflict.current}"
            ),
        ) from None

    _etag(response, page["revision"])
    return page


@router.get("/{slug}/revisions", response_model=list[RevisionSummary])
def list_revisions(slug: str) -> list[dict]:
    """Newest revision first."""
    try:
        return repo.list_revisions(slug)
    except repo.PageNotFound:
        raise _NO_PAGE from None


@router.get("/{slug}/revisions/{revision}", response_model=Revision)
def get_revision(slug: str, revision: int) -> dict:
    try:
        return repo.get_revision(slug, revision)
    except repo.PageNotFound:
        raise _NO_PAGE from None
    except repo.RevisionNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no such revision"
        ) from None
