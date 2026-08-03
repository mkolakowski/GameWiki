"""Smoke tests for the browser UI.

Per the docs-index rule's smoke-test shape: each route must return 200, carry a
recognizable substring from its heading, and render with the nav.
"""

from uuid import uuid4

import pytest

NAV = 'class="nav-brand"'


@pytest.fixture
def slug() -> str:
    return f"web-page-{uuid4().hex[:12]}"


@pytest.fixture
def page(client, slug) -> dict:
    response = client.post(
        "/pages", json={"slug": slug, "title": "Outer Wilds", "body": "A space game."}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_index_lists_pages(client, page, slug):
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert NAV in response.text
    assert "All pages" in response.text
    assert f'href="/w/{slug}"' in response.text


def test_view_page(client, page, slug):
    response = client.get(f"/w/{slug}")

    assert response.status_code == 200
    assert NAV in response.text
    assert "Outer Wilds" in response.text
    assert "A space game." in response.text
    assert f'href="/w/{slug}/history"' in response.text


def test_view_unknown_page_is_404(client, slug):
    assert client.get(f"/w/{slug}").status_code == 404


def test_edit_form_carries_the_revision(client, page, slug):
    response = client.get(f"/w/{slug}/edit")

    assert response.status_code == 200
    assert NAV in response.text
    # The hidden field is what makes the save an optimistic-concurrency check.
    assert '<input type="hidden" name="revision" value="1">' in response.text
    assert "Outer Wilds" in response.text


def test_edit_form_for_unknown_page_is_404(client, slug):
    assert client.get(f"/w/{slug}/edit").status_code == 404


def test_save_redirects_and_persists(client, page, slug, form_post):
    response = form_post(
        client,
        f"/w/{slug}/edit",
        {"revision": "1", "title": "Outer Wilds (2019)", "body": "22 minutes."},
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/w/{slug}"

    saved = client.get(f"/pages/{slug}").json()
    assert saved["title"] == "Outer Wilds (2019)"
    assert saved["body"] == "22 minutes."
    assert saved["revision"] == 2


def test_save_from_a_stale_revision_is_409_and_keeps_the_draft(client, page, slug, form_post):
    """A conflict must not throw away what the editor typed."""
    form_post(client, f"/w/{slug}/edit", {"revision": "1", "title": "Theirs", "body": "theirs"})

    response = form_post(
        client, f"/w/{slug}/edit", {"revision": "1", "title": "Mine", "body": "my draft"}
    )

    assert response.status_code == 409
    assert "Someone else saved this page" in response.text
    # The draft comes back in the form, and the hidden field has advanced.
    assert "my draft" in response.text
    assert '<input type="hidden" name="revision" value="2">' in response.text

    # The losing write did not land.
    assert client.get(f"/pages/{slug}").json()["title"] == "Theirs"


def test_history_lists_revisions_newest_first(client, page, slug, form_post):
    form_post(client, f"/w/{slug}/edit", {"revision": "1", "title": "Second", "body": "b2"})

    response = client.get(f"/w/{slug}/history")

    assert response.status_code == 200
    assert NAV in response.text
    assert "History" in response.text
    assert response.text.index("rev 2") < response.text.index("rev 1")


def test_view_a_historical_revision(client, page, slug, form_post):
    form_post(client, f"/w/{slug}/edit", {"revision": "1", "title": "Overwritten", "body": "new"})

    response = client.get(f"/w/{slug}/revisions/1")

    assert response.status_code == 200
    assert NAV in response.text
    assert "read-only" in response.text
    assert "A space game." in response.text


def test_unknown_revision_view_is_404(client, page, slug):
    assert client.get(f"/w/{slug}/revisions/99").status_code == 404


def test_new_page_form_renders(client):
    response = client.get("/new")

    assert response.status_code == 200
    assert NAV in response.text
    assert "New page" in response.text


def test_create_via_form_redirects(client, slug, form_post):
    response = form_post(client, "/new", {"slug": slug, "title": "Hades", "body": "Roguelike."})

    assert response.status_code == 303
    assert response.headers["location"] == f"/w/{slug}"
    assert client.get(f"/pages/{slug}").json()["title"] == "Hades"


def test_create_via_form_rejects_a_duplicate_slug_and_keeps_the_draft(
    client, page, slug, form_post
):
    response = form_post(client, "/new", {"slug": slug, "title": "Clash", "body": "my draft"})

    assert response.status_code == 400
    assert "already exists" in response.text
    assert "my draft" in response.text


def test_create_via_form_rejects_a_malformed_slug(client, form_post):
    response = form_post(client, "/new", {"slug": "Not A Slug", "title": "Nope"})

    assert response.status_code == 400
    assert "not a valid slug" in response.text


def test_stylesheet_keeps_the_44px_baseline(client):
    """The touch-target rules CLAUDE.md calls load-bearing must stay served."""
    response = client.get("/static/base.css")

    assert response.status_code == 200
    css = response.text
    assert "min-height: 44px" in css
    assert "inline-flex" in css
