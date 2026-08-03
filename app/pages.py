"""Wiki page CRUD.

Pages are addressed by `slug` — the stable natural key. The surrogate `id`
column is never exposed through the API, so clients and tests survive a reseed.
"""

from datetime import datetime

import psycopg
from fastapi import APIRouter, HTTPException, status
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
    updated_at: datetime


class Page(PageSummary):
    body: str


@router.get("", response_model=list[PageSummary])
def list_pages() -> list[dict]:
    with pool.connection() as conn:
        return conn.execute("SELECT slug, title, updated_at FROM pages ORDER BY title").fetchall()


@router.post("", response_model=Page, status_code=status.HTTP_201_CREATED)
def create_page(payload: PageCreate) -> dict:
    with pool.connection() as conn:
        try:
            return conn.execute(
                "INSERT INTO pages (slug, title, body) VALUES (%s, %s, %s)"
                " RETURNING slug, title, body, updated_at",
                (payload.slug, payload.title, payload.body),
            ).fetchone()
        except psycopg.errors.UniqueViolation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"a page with slug {payload.slug!r} already exists",
            ) from None


@router.get("/{slug}", response_model=Page)
def get_page(slug: str) -> dict:
    with pool.connection() as conn:
        page = conn.execute(
            "SELECT slug, title, body, updated_at FROM pages WHERE slug = %s", (slug,)
        ).fetchone()

    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such page")
    return page


@router.put("/{slug}", response_model=Page)
def update_page(slug: str, payload: PageUpdate) -> dict:
    with pool.connection() as conn:
        page = conn.execute(
            "UPDATE pages SET title = %s, body = %s, updated_at = now()"
            " WHERE slug = %s RETURNING slug, title, body, updated_at",
            (payload.title, payload.body, slug),
        ).fetchone()

    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such page")
    return page
