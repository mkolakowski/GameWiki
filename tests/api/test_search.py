"""Full-text search, on both the HTML and JSON surfaces.

Every test seeds its own pages with a nonce word so the assertions survive a
database that already holds unrelated content — the suite runs against a
long-lived dev instance, not a fresh one.
"""

from uuid import uuid4

import pytest

NAV = 'class="nav-brand"'


@pytest.fixture
def nonce() -> str:
    """A word no other page contains, so a search for it isolates this test."""
    return f"zqx{uuid4().hex[:10]}"


@pytest.fixture
def make_page(client):
    def create(slug: str, title: str, body: str) -> dict:
        response = client.post("/pages", json={"slug": slug, "title": title, "body": body})
        assert response.status_code == 201, response.text
        return response.json()

    return create


def test_search_finds_a_page_by_body_text(client, make_page, nonce):
    slug = f"search-{nonce}"
    make_page(slug, "Outer Wilds", f"A space exploration game about {nonce} time loops.")

    response = client.get("/search", params={"q": nonce})

    assert response.status_code == 200
    assert NAV in response.text
    assert "Search" in response.text
    assert f'href="/w/{slug}"' in response.text
    assert "1 result" in response.text


def test_search_marks_the_matching_term_in_the_snippet(client, make_page, nonce):
    make_page(f"snippet-{nonce}", "Hades", f"A roguelike where {nonce} means escaping.")

    response = client.get("/search", params={"q": nonce})

    assert response.status_code == 200
    # The snippet is the whole point of the results page — a bare title list
    # would not tell you why a page matched.
    assert f"<mark>{nonce}</mark>" in response.text


def test_title_matches_outrank_body_mentions(client, make_page, nonce):
    """Weighting is the reason the migration uses setweight, so assert it."""
    # The first page mentions the term only in its body, the second names
    # itself for it — so the nonce must stay out of the first page's title.
    make_page(f"body-{nonce}", "Some Other Game", f"It is a bit like {nonce} in places.")
    make_page(f"title-{nonce}", f"{nonce} Chronicles", "An unrelated blurb.")

    response = client.get("/pages", params={"q": nonce})

    assert response.status_code == 200
    slugs = [row["slug"] for row in response.json()]
    assert slugs[0] == f"title-{nonce}", slugs


def test_search_json_returns_page_summaries(client, make_page, nonce):
    slug = f"json-{nonce}"
    make_page(slug, "Celeste", f"A platformer about {nonce} and a mountain.")

    response = client.get("/pages", params={"q": nonce})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["slug"] == slug
    assert body[0]["title"] == "Celeste"
    assert body[0]["revision"] == 1
    assert "updated_at" in body[0]


def test_pages_without_a_query_still_lists_everything(client, make_page, nonce):
    """The list endpoint gained ?q= — its existing contract must not shift."""
    slug = f"listing-{nonce}"
    make_page(slug, "Tunic", "A fox with a manual.")

    unfiltered = client.get("/pages")

    assert unfiltered.status_code == 200
    slugs = [row["slug"] for row in unfiltered.json()]
    assert slug in slugs
    assert len(slugs) > 1


def test_blank_query_is_not_treated_as_a_search(client):
    """Whitespace must fall through to the full listing, not match nothing."""
    assert len(client.get("/pages", params={"q": "   "}).json()) > 0


def test_search_reflects_an_edit(client, make_page, nonce):
    """The generated column has no application-side maintenance — prove it."""
    slug = f"edit-{nonce}"
    make_page(slug, "Before", "nothing interesting here")
    client.put(f"/pages/{slug}", json={"title": "After", "body": f"now mentions {nonce}"})

    matches = client.get("/pages", params={"q": nonce}).json()

    assert [row["slug"] for row in matches] == [slug]


def test_search_with_no_matches_offers_to_create_the_page(client, nonce):
    response = client.get("/search", params={"q": nonce})

    assert response.status_code == 200
    assert "Nothing matches" in response.text
    assert f"/new?slug={nonce}" in response.text


def test_search_page_without_a_query_prompts_instead_of_erroring(client):
    response = client.get("/search")

    assert response.status_code == 200
    assert NAV in response.text
    assert "Type a query" in response.text


def test_punctuation_soup_is_zero_results_not_a_500(client):
    """websearch_to_tsquery degrades to an empty query; to_tsquery would raise."""
    response = client.get("/search", params={"q": "&&& ||| !!! <>"})

    assert response.status_code == 200
    assert "Nothing matches" in response.text

    assert client.get("/pages", params={"q": "&&& ||| :*"}).status_code == 200


def test_quoted_phrase_search(client, make_page, nonce):
    make_page(f"phrase-a-{nonce}", f"Phrase A {nonce}", f"the {nonce} silent cartographer")
    make_page(
        f"phrase-b-{nonce}", f"Phrase B {nonce}", f"silent, and separately {nonce} cartographer"
    )

    matches = client.get("/pages", params={"q": f'"{nonce} silent cartographer"'}).json()

    assert [row["slug"] for row in matches] == [f"phrase-a-{nonce}"]


def test_search_is_readable_while_signed_out(anon_client, client, make_page, nonce):
    """Reads stay public — search must not be gated behind the editor role."""
    make_page(f"anon-{nonce}", "Public Page", f"readable by anyone, mentions {nonce}")

    response = anon_client.get("/search", params={"q": nonce})

    assert response.status_code == 200
    assert f"anon-{nonce}" in response.text


def test_unknown_search_route_is_still_404(client):
    """/search must not swallow neighbouring paths."""
    assert client.get("/search/nope").status_code == 404


def test_hostile_body_is_escaped_in_the_snippet(client, make_page, nonce, assert_safe_html):
    """The snippet is a slice of a user-authored body reaching the browser as
    HTML — the same risk surface the markdown pipeline carries."""
    payload = f"<script>alert(1)</script><img src=x onerror=alert(2)> {nonce}"
    make_page(f"xss-{nonce}", "Hostile", payload)

    response = client.get("/search", params={"q": nonce})

    assert response.status_code == 200
    assert_safe_html(response.text)


def test_hostile_title_is_escaped_in_the_results(client, make_page, nonce, assert_safe_html):
    make_page(f"xss-title-{nonce}", f"<script>alert(1)</script> {nonce}", f"body {nonce}")

    response = client.get("/search", params={"q": nonce})

    assert response.status_code == 200
    assert_safe_html(response.text)


def test_a_crafted_query_cannot_inject_markup(client, make_page, nonce, assert_safe_html):
    """The query is echoed back in the results heading and the nav search box."""
    make_page(f"echo-{nonce}", "Echo", f"a page mentioning {nonce}")

    response = client.get("/search", params={"q": f'{nonce} "><script>alert(1)</script>'})

    assert response.status_code == 200
    assert_safe_html(response.text)
