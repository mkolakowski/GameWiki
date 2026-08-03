"""Smoke and contract tests for the documentation surface.

The shape CLAUDE.md's docs-index rule asks for: every slug returns 200, carries
a recognizable substring from its H1, and renders with the nav — plus an
index-page assertion so a regression that drops a row gets caught.

The parametrisation is driven from `app.docs.DOCS` rather than a hand-written
list, so a document added to the allowlist without an index row, or vice
versa, fails here instead of shipping unreachable.
"""

import pytest

from app.docs import DOCS

NAV = 'class="nav-brand"'
HTML = {"accept": "text/html"}

# The H1 each document should render, keyed by slug. Hardcoded on purpose:
# deriving it from the file would assert the code against itself.
HEADINGS = {
    "readme": "GameWiki",
    "changelog": "Changelog",
    "guidelines": "GameWiki — Claude Code guidelines",
}


def test_every_allowlisted_doc_has_an_expected_heading():
    """Keeps HEADINGS honest when a doc is added to DOCS."""
    assert set(HEADINGS) == set(DOCS)


@pytest.mark.parametrize("slug", sorted(DOCS))
def test_doc_renders(anon_client, slug):
    response = anon_client.get(f"/docs/{slug}", headers=HTML)

    assert response.status_code == 200
    assert NAV in response.text
    assert HEADINGS[slug] in response.text


@pytest.mark.parametrize("slug", sorted(DOCS))
def test_index_links_every_doc(anon_client, slug):
    """A doc missing from the index is a doc nobody can find."""
    response = anon_client.get("/docs", headers=HTML)

    assert response.status_code == 200
    assert f'href="/docs/{slug}"' in response.text


def test_index_renders_with_nav_and_heading(anon_client):
    response = anon_client.get("/docs", headers=HTML)

    assert response.status_code == 200
    assert NAV in response.text
    assert "Documentation" in response.text


def test_docs_are_public(anon_client):
    """Docs are reference material — gating them behind sign-in helps nobody."""
    assert anon_client.get("/docs").status_code == 200
    assert anon_client.get("/docs/readme").status_code == 200


def test_unknown_slug_is_404(anon_client):
    assert anon_client.get("/docs/nope").status_code == 404


@pytest.mark.parametrize(
    "attempt",
    [
        "../pyproject.toml",
        "..%2Fpyproject.toml",
        "....//pyproject.toml",
        "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "/etc/passwd",
    ],
)
def test_a_slug_cannot_escape_the_allowlist(anon_client, attempt):
    """Slugs index a fixed dict; nothing user-supplied reaches the filesystem."""
    response = anon_client.get(f"/docs/{attempt}")

    assert response.status_code in (404, 307, 308), response.text
    assert "hatchling" not in response.text
    assert "root:" not in response.text


def test_the_openapi_ui_moved_off_the_docs_namespace(anon_client):
    """FastAPI mounts Swagger at /docs by default and wins over the router, so
    it was moved rather than left to shadow the documentation index."""
    assert anon_client.get("/api-docs").status_code == 200
    assert anon_client.get("/openapi.json").status_code == 200

    index = anon_client.get("/docs", headers=HTML)
    assert "swagger" not in index.text.lower()


def test_the_nav_links_to_the_docs_index(anon_client):
    response = anon_client.get("/", headers=HTML)

    assert response.status_code == 200
    assert 'href="/docs"' in response.text


# --- rendering ---------------------------------------------------------------


def test_the_guidelines_tables_render_as_tables(anon_client):
    """The guidelines are mostly tables, and the commonmark preset has none —
    which is why documents render on their own markdown-it instance."""
    response = anon_client.get("/docs/guidelines", headers=HTML)

    assert "<table>" in response.text
    assert "app/version.py" in response.text


def test_documented_wiki_link_syntax_is_not_rewritten(anon_client):
    """The changelog documents `[[Page Title]]` in backticks. The page renderer
    would turn that into a red link, because resolution runs over the raw
    source before markdown parsing — so docs must not go through it."""
    response = anon_client.get("/docs/changelog", headers=HTML)

    assert response.status_code == 200
    assert "[[Page Title]]" in response.text
    assert "/new?slug=page-title" not in response.text


def test_relative_links_between_docs_are_rewritten(anon_client):
    """`[Changelog](CHANGELOG.md)` in the README would resolve to /docs/CHANGELOG.md."""
    response = anon_client.get("/docs/readme", headers=HTML)

    assert 'href="/docs/changelog"' in response.text
    assert 'href="CHANGELOG.md"' not in response.text


def test_docs_render_no_dangerous_markup(anon_client, assert_safe_html):
    """Docs are repo files rather than user input, but they still go through
    nh3 — 'trusted' describes today's file list, not the code path."""
    for slug in DOCS:
        assert_safe_html(anon_client.get(f"/docs/{slug}", headers=HTML).text)


def test_the_readme_badge_matches_the_running_version(anon_client):
    """scripts/check_release.py enforces this at commit time; this catches a
    running instance serving a README that disagrees with itself."""
    version = anon_client.get("/health").json()["version"]
    readme = anon_client.get("/docs/readme", headers=HTML).text

    assert f"badge/version-{version}-" in readme
