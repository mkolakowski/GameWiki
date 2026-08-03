"""Contract tests for the /pages surface.

Pages are always looked up by slug, never by a hardcoded id, so these survive a
reseed. Slugs are unique per run because the surface has no DELETE yet — see
the note in CHANGELOG 0.3.0.
"""

from uuid import uuid4

import pytest


@pytest.fixture
def slug() -> str:
    return f"test-page-{uuid4().hex[:12]}"


@pytest.fixture
def page(client, slug) -> dict:
    """A freshly created page, returned as the POST response body."""
    response = client.post(
        "/pages", json={"slug": slug, "title": "Chrono Trigger", "body": "A JRPG."}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_page(page, slug):
    """Happy path: 201, full body shape, and the fields a client reads."""
    assert set(page) == {"slug", "title", "body", "updated_at"}
    assert page["slug"] == slug
    assert page["title"] == "Chrono Trigger"
    assert page["body"] == "A JRPG."
    assert page["updated_at"]


def test_get_page_by_slug(client, page, slug):
    response = client.get(f"/pages/{slug}")

    assert response.status_code == 200
    assert response.json() == page


def test_list_pages_includes_the_new_page(client, page, slug):
    response = client.get("/pages")

    assert response.status_code == 200
    listing = response.json()
    assert isinstance(listing, list)

    match = next((p for p in listing if p["slug"] == slug), None)
    assert match is not None, "created page missing from the listing"

    # The listing is a summary — body is deliberately not carried.
    assert set(match) == {"slug", "title", "updated_at"}
    assert match["title"] == "Chrono Trigger"


def test_update_page(client, page, slug):
    response = client.put(
        f"/pages/{slug}", json={"title": "Chrono Trigger (SNES)", "body": "1995."}
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["slug"] == slug
    assert updated["title"] == "Chrono Trigger (SNES)"
    assert updated["body"] == "1995."
    assert updated["updated_at"] >= page["updated_at"]

    # The write actually landed, not just echoed back.
    assert client.get(f"/pages/{slug}").json() == updated


def test_duplicate_slug_is_409(client, page, slug):
    """The contract-specific conflict: slug is unique."""
    response = client.post("/pages", json={"slug": slug, "title": "Something Else"})

    assert response.status_code == 409
    assert slug in response.json()["detail"]


def test_get_unknown_slug_is_404(client, slug):
    response = client.get(f"/pages/{slug}")

    assert response.status_code == 404
    assert response.json()["detail"] == "no such page"


def test_update_unknown_slug_is_404(client, slug):
    response = client.put(f"/pages/{slug}", json={"title": "Ghost"})

    assert response.status_code == 404


def test_create_rejects_missing_title(client, slug):
    response = client.post("/pages", json={"slug": slug})

    assert response.status_code == 422


def test_create_rejects_malformed_slug(client):
    """Slugs are lowercase, digits, and single hyphens — nothing else."""
    response = client.post("/pages", json={"slug": "Not A Slug", "title": "Nope"})

    assert response.status_code == 422
