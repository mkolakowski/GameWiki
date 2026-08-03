"""Contract tests for Google OIDC sign-in and the write gate.

These run against the stub provider in devtools/fake_oidc.py, which speaks real
OIDC — discovery, JWKS, code exchange, RS256 id_token — so the app's Authlib
path is exercised rather than bypassed. What they cannot prove is that the app
works against Google itself; see CHANGELOG 0.7.0.
"""

from uuid import uuid4

import pytest

HTML = {"accept": "text/html"}


@pytest.fixture
def slug() -> str:
    return f"auth-page-{uuid4().hex[:12]}"


# --- the write gate --------------------------------------------------------


def test_anonymous_cannot_create_via_the_api(anon_client, slug):
    response = anon_client.post("/pages", json={"slug": slug, "title": "Nope"})

    assert response.status_code == 401
    assert "sign in" in response.json()["detail"]


def test_anonymous_cannot_update_via_the_api(client, anon_client, slug):
    client.post("/pages", json={"slug": slug, "title": "Mine"})

    response = anon_client.put(f"/pages/{slug}", json={"title": "Hijacked"})

    assert response.status_code == 401
    assert client.get(f"/pages/{slug}").json()["title"] == "Mine"


def test_anonymous_cannot_post_the_edit_form(client, anon_client, slug):
    client.post("/pages", json={"slug": slug, "title": "Mine"})

    response = anon_client.post(
        f"/w/{slug}/edit", data={"revision": "1", "title": "Hijacked", "body": ""}
    )

    assert response.status_code in (401, 303)
    assert client.get(f"/pages/{slug}").json()["title"] == "Mine"


def test_anonymous_reads_are_still_allowed(client, anon_client, slug):
    client.post("/pages", json={"slug": slug, "title": "Public", "body": "readable"})

    assert anon_client.get("/pages").status_code == 200
    assert anon_client.get(f"/pages/{slug}").status_code == 200
    assert anon_client.get(f"/w/{slug}").status_code == 200
    assert anon_client.get(f"/w/{slug}/history").status_code == 200
    assert anon_client.get("/").status_code == 200


def test_a_browser_hitting_edit_is_sent_to_sign_in(anon_client, client, slug):
    """A JSON 401 is a dead end for someone who clicked Edit."""
    client.post("/pages", json={"slug": slug, "title": "Mine"})

    response = anon_client.get(f"/w/{slug}/edit", headers=HTML)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/auth/login?next=")


def test_an_api_client_gets_json_not_a_redirect(anon_client, slug):
    """The same 401 must stay machine-readable without an HTML Accept header."""
    response = anon_client.post("/pages", json={"slug": slug, "title": "Nope"})

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")


# --- the sign-in flow ------------------------------------------------------


def test_sign_in_puts_the_user_in_the_nav(client):
    html = client.get("/", headers=HTML).text

    assert "Ada Lovelace" in html
    assert "Sign out" in html
    assert "Sign in with Google" not in html


def test_anonymous_nav_offers_sign_in(anon_client):
    html = anon_client.get("/", headers=HTML).text

    assert "Sign in with Google" in html
    assert "Sign out" not in html


def test_sign_out_clears_the_session(client, slug):
    assert client.post("/pages", json={"slug": slug, "title": "Yes"}).status_code == 201

    logout = client.get("/auth/logout")
    assert logout.status_code == 303

    after = client.post("/pages", json={"slug": f"{slug}-2", "title": "No"})
    assert after.status_code == 401


def test_login_only_redirects_to_same_site_paths(client):
    """A crafted ?next= must not bounce a signed-in user to another origin."""
    response = client.get(
        "/auth/login", params={"next": "https://evil.example/steal"}, follow_redirects=True
    )

    assert response.status_code == 200
    assert str(response.url).startswith("http://localhost:8000")


def test_health_reports_that_auth_is_configured(anon_client):
    assert anon_client.get("/health").json()["auth_configured"] is True


# --- authorship ------------------------------------------------------------


def test_the_creating_user_is_recorded_as_the_author(client, slug):
    client.post("/pages", json={"slug": slug, "title": "Attributed"})

    history = client.get(f"/pages/{slug}/revisions").json()

    assert history[0]["author"] == "Ada Lovelace"


def test_each_revision_records_its_own_author(client, sign_in_as, slug):
    client.post("/pages", json={"slug": slug, "title": "First"})

    grace = sign_in_as("google-oauth2|000000000000000000002", "grace@example.com", "Grace Hopper")
    assert grace.put(f"/pages/{slug}", json={"title": "Second"}).status_code == 200

    history = client.get(f"/pages/{slug}/revisions").json()

    assert [r["revision"] for r in history] == [2, 1]
    assert history[0]["author"] == "Grace Hopper"
    assert history[1]["author"] == "Ada Lovelace"


def test_the_history_page_shows_authors(client, sign_in_as, slug):
    client.post("/pages", json={"slug": slug, "title": "First"})
    grace = sign_in_as("google-oauth2|000000000000000000002", "grace@example.com", "Grace Hopper")
    grace.put(f"/pages/{slug}", json={"title": "Second"})

    html = client.get(f"/w/{slug}/history", headers=HTML).text

    assert "Grace Hopper" in html
    assert "Ada Lovelace" in html


def test_signing_in_twice_reuses_one_user_row(client, sign_in_as, slug):
    """(issuer, subject) is the identity — a second sign-in must not fork it."""
    again = sign_in_as("google-oauth2|000000000000000000001", "ada@example.com", "Ada Lovelace")
    again.post("/pages", json={"slug": slug, "title": "Same person"})

    history = client.get(f"/pages/{slug}/revisions").json()
    assert history[0]["author"] == "Ada Lovelace"


def test_a_changed_display_name_follows_the_same_user(client, sign_in_as, slug):
    renamed = sign_in_as("google-oauth2|000000000000000000001", "ada@example.com", "Ada King")
    renamed.post("/pages", json={"slug": slug, "title": "Renamed"})

    history = client.get(f"/pages/{slug}/revisions").json()
    assert history[0]["author"] == "Ada King"


def test_a_hostile_display_name_is_escaped_in_history(sign_in_as, client, slug, assert_safe_html):
    hostile = sign_in_as(
        "google-oauth2|000000000000000000003",
        "evil@allowed.example",
        "<script>alert(1)</script>",
    )
    hostile.post("/pages", json={"slug": slug, "title": "Written by a hostile name"})

    assert_safe_html(client.get(f"/w/{slug}/history", headers=HTML).text)
    assert_safe_html(hostile.get("/", headers=HTML).text)


# --- provider key rotation -------------------------------------------------


def test_sign_in_survives_a_provider_key_rotation(anon_client, oidc_base_url, base_url):
    """Google rotates signing keys; a cached JWK set must not wedge sign-in.

    Authlib caches the key set on the client indefinitely, so before this was
    handled a rotation turned every sign-in into a 500 until the process
    restarted. The spent authorization code means the failing attempt can't be
    salvaged — what matters is that it fails cleanly and the next one works.
    """
    import httpx

    httpx.post(f"{oidc_base_url}/_test/rotate_key", timeout=10.0).raise_for_status()

    first = anon_client.get("/auth/login", params={"next": "/"}, follow_redirects=True)
    assert first.status_code in (200, 400), first.status_code
    assert first.status_code != 500

    # Whatever happened above, a fresh attempt must succeed.
    with httpx.Client(base_url=base_url, timeout=15.0) as retry:
        httpx.post(
            f"{oidc_base_url}/_test/identity",
            json={"sub": "rotate|1", "email": "rot@example.com", "name": "Rota Ted"},
            timeout=10.0,
        ).raise_for_status()
        response = retry.get("/auth/login", params={"next": "/"}, follow_redirects=True)

        assert response.status_code == 200
        assert "Rota Ted" in retry.get("/", headers=HTML).text
