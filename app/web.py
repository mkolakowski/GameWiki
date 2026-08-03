"""The browser UI.

Server-rendered HTML over the same repository layer the JSON API uses. Routes
live under `/w/` so they can't collide with the API's `/pages/` namespace.

Edits carry the revision they started from in a hidden field, which becomes the
optimistic-concurrency check on save — the form equivalent of `If-Match`.
"""

import re

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import markup
from app import repository as repo
from app.auth import current_user, require_user
from app.version import APP_VERSION, APP_VERSION_NAME

router = APIRouter(tags=["web"])


def _user_context(request: Request) -> dict:
    """Every template needs to know who is signed in, for the nav."""
    return {"user": current_user(request)}


templates = Jinja2Templates(directory="app/templates", context_processors=[_user_context])
templates.env.globals["app_version"] = APP_VERSION
templates.env.globals["app_version_name"] = APP_VERSION_NAME

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_NO_PAGE = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such page")


def _see_other(url: str) -> RedirectResponse:
    """POST-then-redirect, so a refresh doesn't resubmit the form."""
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _render_body(body: str) -> str:
    """Sanitised HTML for a page body, with wiki links resolved."""
    return markup.render(body, repo.existing_slugs(markup.extract_links(body)))


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"pages": repo.list_pages()})


@router.get("/new", response_class=HTMLResponse)
def new_page_form(request: Request, slug: str = "", title: str = ""):
    """Red links arrive here with slug and title prefilled from the link text."""
    require_user(request)
    return templates.TemplateResponse(
        request, "new.html", {"slug": slug, "title": title, "body": "", "error": None}
    )


@router.post("/new")
def create_page(
    request: Request,
    slug: str = Form(...),
    title: str = Form(...),
    body: str = Form(""),
):
    author = require_user(request)

    def reject(message: str):
        # Re-render with the user's text intact rather than losing their draft.
        return templates.TemplateResponse(
            request,
            "new.html",
            {"slug": slug, "title": title, "body": body, "error": message},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not SLUG_RE.match(slug):
        return reject(
            f"{slug!r} is not a valid slug — use lowercase letters, digits, and single hyphens."
        )
    if not title.strip():
        return reject("A title is required.")

    try:
        repo.create_page(slug, title, body, author["id"])
    except repo.SlugTaken:
        return reject(f"A page with the slug {slug!r} already exists.")

    return _see_other(f"/w/{slug}")


@router.get("/w/{slug}", response_class=HTMLResponse)
def view_page(request: Request, slug: str):
    try:
        page = repo.get_page(slug)
    except repo.PageNotFound:
        raise _NO_PAGE from None

    return templates.TemplateResponse(
        request,
        "page.html",
        {
            "page": page,
            "body_html": _render_body(page["body"]),
            "backlinks": repo.backlinks(slug),
        },
    )


@router.get("/w/{slug}/edit", response_class=HTMLResponse)
def edit_page_form(request: Request, slug: str):
    require_user(request)
    try:
        page = repo.get_page(slug)
    except repo.PageNotFound:
        raise _NO_PAGE from None

    return templates.TemplateResponse(
        request,
        "edit.html",
        {
            "slug": page["slug"],
            "title": page["title"],
            "body": page["body"],
            "revision": page["revision"],
            "conflict": None,
        },
    )


@router.post("/w/{slug}/edit")
def save_page(
    request: Request,
    slug: str,
    revision: int = Form(...),
    title: str = Form(...),
    body: str = Form(""),
):
    author = require_user(request)
    try:
        repo.update_page(slug, title, body, expected_revision=revision, author_id=author["id"])
    except repo.PageNotFound:
        raise _NO_PAGE from None
    except repo.RevisionConflict as conflict:
        # Hand the draft back rather than discarding it. The hidden field is
        # advanced to the current revision so a deliberate re-save can land.
        return templates.TemplateResponse(
            request,
            "edit.html",
            {
                "slug": slug,
                "title": title,
                "body": body,
                "revision": conflict.current,
                "conflict": {"expected": conflict.expected, "current": conflict.current},
            },
            status_code=status.HTTP_409_CONFLICT,
        )

    return _see_other(f"/w/{slug}")


@router.get("/w/{slug}/history", response_class=HTMLResponse)
def page_history(request: Request, slug: str):
    try:
        page = repo.get_page(slug)
        revisions = repo.list_revisions(slug)
    except repo.PageNotFound:
        raise _NO_PAGE from None

    return templates.TemplateResponse(
        request, "history.html", {"page": page, "revisions": revisions}
    )


@router.get("/w/{slug}/revisions/{revision}", response_class=HTMLResponse)
def view_revision(request: Request, slug: str, revision: int):
    try:
        row = repo.get_revision(slug, revision)
    except repo.PageNotFound:
        raise _NO_PAGE from None
    except repo.RevisionNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no such revision"
        ) from None

    return templates.TemplateResponse(
        request,
        "revision.html",
        {"slug": slug, "revision": row, "body_html": _render_body(row["body"])},
    )
