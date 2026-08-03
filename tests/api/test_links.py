"""Contract tests for wiki links and backlinks through the running app."""

from uuid import uuid4

import pytest


@pytest.fixture
def slugs() -> dict:
    stamp = uuid4().hex[:12]
    return {"source": f"link-src-{stamp}", "target": f"link-dst-{stamp}"}


def make_page(client, slug, title, body=""):
    response = client.post("/pages", json={"slug": slug, "title": title, "body": body})
    assert response.status_code == 201, response.text
    return response.json()


def test_link_to_an_existing_page_renders_as_a_link(client, slugs):
    make_page(client, slugs["target"], "Target Page")
    make_page(client, slugs["source"], "Source Page", f"See [[{slugs['target']}]].")

    html = client.get(f"/w/{slugs['source']}").text

    assert f'href="/w/{slugs["target"]}"' in html


def test_link_to_a_missing_page_is_a_red_link_to_the_prefilled_form(client, slugs):
    make_page(client, slugs["source"], "Source Page", f"See [[{slugs['target']}]].")

    html = client.get(f"/w/{slugs['source']}").text

    assert f"/new?slug={slugs['target']}" in html
    assert f'href="/w/{slugs["target"]}"' not in html


def test_a_red_link_lights_up_once_the_target_is_created(client, slugs):
    make_page(client, slugs["source"], "Source Page", f"See [[{slugs['target']}]].")
    assert f"/new?slug={slugs['target']}" in client.get(f"/w/{slugs['source']}").text

    make_page(client, slugs["target"], "Target Page")

    html = client.get(f"/w/{slugs['source']}").text
    assert f'href="/w/{slugs["target"]}"' in html
    assert f"/new?slug={slugs['target']}" not in html


def test_backlinks_appear_on_the_target(client, slugs):
    make_page(client, slugs["target"], "Target Page")
    make_page(client, slugs["source"], "Source Page", f"See [[{slugs['target']}]].")

    html = client.get(f"/w/{slugs['target']}").text

    assert "What links here" in html
    assert f'href="/w/{slugs["source"]}"' in html
    assert "Source Page" in html


def test_backlinks_follow_an_edit_that_removes_the_link(client, slugs):
    make_page(client, slugs["target"], "Target Page")
    make_page(client, slugs["source"], "Source Page", f"See [[{slugs['target']}]].")
    assert "What links here" in client.get(f"/w/{slugs['target']}").text

    client.put(f"/pages/{slugs['source']}", json={"title": "Source Page", "body": "no links now"})

    assert "What links here" not in client.get(f"/w/{slugs['target']}").text


def test_a_page_with_no_backlinks_omits_the_section(client, slugs):
    make_page(client, slugs["target"], "Target Page")

    assert "What links here" not in client.get(f"/w/{slugs['target']}").text


def test_markdown_renders_in_a_page_body(client, slugs):
    make_page(client, slugs["source"], "Source Page", "## Sub heading\n\n**bold**")

    html = client.get(f"/w/{slugs['source']}").text

    assert "<h2>Sub heading</h2>" in html
    assert "<strong>bold</strong>" in html


def test_stored_script_in_a_body_is_not_served_as_html(client, slugs, assert_safe_html):
    """Stored XSS check against the running app, not just the renderer."""
    make_page(
        client,
        slugs["source"],
        "Source Page",
        '<script>alert(1)</script>\n\n<img src=x onerror="alert(2)">\n\n'
        "[x](javascript:alert3)\n\n"
        '[[Nope" onmouseover="alert(4)]]',
    )

    assert_safe_html(client.get(f"/w/{slugs['source']}").text)


def test_a_hostile_title_is_escaped_in_the_prefilled_form(client, assert_safe_html):
    """Red-link text reaches /new as a query param and lands in an attribute."""
    response = client.get('/new?slug=x-y&title=Nope" onmouseover="alert(1)')

    assert response.status_code == 200
    assert_safe_html(response.text)


def test_a_hostile_title_is_escaped_in_page_and_history_views(client, slugs, assert_safe_html):
    """Titles are rendered in headings, listings, and the <title> element."""
    make_page(client, slugs["source"], "<script>alert(1)</script>", "body")
    client.put(f"/pages/{slugs['source']}", json={"title": '"><script>alert(2)</script>'})

    for path in ("/", f"/w/{slugs['source']}", f"/w/{slugs['source']}/history"):
        assert_safe_html(client.get(path).text)


def test_the_prefilled_create_form_carries_the_link_text(client, slugs):
    response = client.get(f"/new?slug={slugs['target']}&title=Target+Page")

    assert response.status_code == 200
    assert f'value="{slugs["target"]}"' in response.text
    assert 'value="Target Page"' in response.text
