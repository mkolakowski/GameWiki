"""Repo documentation, served through the app.

`/docs` is the single discovery surface CLAUDE.md's docs-index rule asks for.
Serving it through the app rather than leaving `docs/index.md` on disk is what
makes it a discovery surface at all — a markdown file in a directory is barely
more findable than the files it lists.

**Slugs are an allowlist, never a path.** `DOCS` maps a fixed slug to a fixed
repo-relative path, and an unknown slug is a 404 before any filesystem access.
Nothing user-supplied reaches `Path`, so `..` and absolute paths have no route
in. Adding a document means adding a row here, which is exactly the coupling
the rule is after: the doc and its index entry land in the same commit or the
doc is unreachable.
"""

from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app import markup
from app.web import templates

router = APIRouter(prefix="/docs", tags=["docs"])

# The repo root, two levels up from this file (app/docs.py).
REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Doc:
    slug: str
    path: str
    title: str
    group: str
    status: str
    summary: str


# Grouped by doc type, per the rule's "guides, design plans, references, repo
# documentation". Only repo documentation exists so far; the groups appear as
# headings on the index as soon as something fills them.
DOCS: dict[str, Doc] = {
    "readme": Doc(
        slug="readme",
        path="README.md",
        title="README",
        group="Repo documentation",
        status="✅ shipped",
        summary="What GameWiki is, how to run it, and how the pieces fit together.",
    ),
    "changelog": Doc(
        slug="changelog",
        path="CHANGELOG.md",
        title="Changelog",
        group="Repo documentation",
        status="✅ shipped",
        summary="Every release, newest first, with the reasoning behind each one.",
    ),
    "guidelines": Doc(
        slug="guidelines",
        path="CLAUDE.md",
        title="Project guidelines",
        group="Repo documentation",
        status="✅ shipped",
        summary="The conventions this repo is built to — versioning, tests, touch targets.",
    ),
}

# Relative links between repo docs would resolve against /docs/ and 404, so
# each known filename is rewritten to the slug it is served under.
_LINK_REWRITES = {f"]({doc.path})": f"](/docs/{doc.slug})" for doc in DOCS.values()}


def _read(doc: Doc) -> str:
    text = (REPO_ROOT / doc.path).read_text(encoding="utf-8")
    for old, new in _LINK_REWRITES.items():
        text = text.replace(old, new)
    return text


def groups() -> dict[str, list[Doc]]:
    """Docs by group, for the index. Insertion order is the display order."""
    grouped: dict[str, list[Doc]] = {}
    for doc in DOCS.values():
        grouped.setdefault(doc.group, []).append(doc)
    return grouped


@router.get("", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "docs_index.html", {"groups": groups()})


@router.get("/{slug}", response_class=HTMLResponse)
def view_doc(request: Request, slug: str):
    doc = DOCS.get(slug)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such document")

    return templates.TemplateResponse(
        request,
        "doc.html",
        {"doc": doc, "body_html": markup.render_document(_read(doc))},
    )
