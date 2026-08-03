"""CSRF protection on the HTML form surface.

These tests are load-bearing in the same way the escaping tests are: a failure
here means a cross-site page can drive a signed-in editor's browser into
writing to this wiki, not that a form looks wrong.

`SameSite=Lax` is not what is under test — the suite is an HTTP client and has
no site of its own, so it can forge what a browser would refuse to send. That
is precisely the point: the token has to hold on its own.
"""

from uuid import uuid4

import pytest

HTML = {"accept": "text/html"}


@pytest.fixture
def slug() -> str:
    return f"csrf-{uuid4().hex[:12]}"


@pytest.fixture
def page(client, slug) -> dict:
    response = client.post("/pages", json={"slug": slug, "title": "Tunic", "body": "A fox."})
    assert response.status_code == 201, response.text
    return response.json()


# --- the token is present where a browser would look for it -----------------


@pytest.mark.parametrize("path", ["/new", "/admin/users"])
def test_forms_carry_a_hidden_token(client, path):
    """A template that drops the field locks its own form out."""
    response = client.get(path, headers=HTML)

    assert response.status_code == 200
    assert 'name="csrf_token"' in response.text


def test_the_edit_form_carries_a_hidden_token(client, page, slug):
    response = client.get(f"/w/{slug}/edit", headers=HTML)

    assert response.status_code == 200
    assert 'name="csrf_token"' in response.text


def test_anonymous_readers_are_not_issued_a_token(anon_client):
    """Minting one for a visitor with no form to submit just costs a cookie."""
    response = anon_client.get("/", headers=HTML)

    assert response.status_code == 200
    assert "csrf_token" not in response.text
    assert "session" not in response.headers.get("set-cookie", "")


# --- writes are refused without a valid token -------------------------------


def test_create_without_a_token_is_refused(client, slug):
    response = client.post("/new", data={"slug": slug, "title": "Forged", "body": "x"})

    assert response.status_code == 403
    assert client.get(f"/pages/{slug}").status_code == 404


def test_create_with_a_wrong_token_is_refused(client, slug):
    response = client.post(
        "/new", data={"slug": slug, "title": "Forged", "body": "x", "csrf_token": "not-the-token"}
    )

    assert response.status_code == 403
    assert client.get(f"/pages/{slug}").status_code == 404


def test_edit_without_a_token_is_refused(client, page, slug):
    response = client.post(
        f"/w/{slug}/edit", data={"revision": "1", "title": "Forged", "body": "forged"}
    )

    assert response.status_code == 403
    # The page is untouched — still revision 1, still the original text.
    saved = client.get(f"/pages/{slug}").json()
    assert saved["revision"] == 1
    assert saved["title"] == "Tunic"


def test_a_refused_edit_keeps_the_draft(client, page, slug):
    """Same value the 409 conflict path protects: never lose an editor's typing."""
    response = client.post(
        f"/w/{slug}/edit", data={"revision": "1", "title": "Mine", "body": "my long draft"}
    )

    assert response.status_code == 403
    assert "my long draft" in response.text
    # And the re-rendered form carries a usable token, so a resubmit works.
    assert 'name="csrf_token"' in response.text


def test_a_refused_create_keeps_the_draft(client, slug):
    response = client.post("/new", data={"slug": slug, "title": "Mine", "body": "my long draft"})

    assert response.status_code == 403
    assert "my long draft" in response.text
    assert 'name="csrf_token"' in response.text


def test_a_role_change_without_a_token_is_refused(client):
    """The highest-value form on the site — privilege escalation lives here."""
    accounts = client.get("/admin/users", headers=HTML)
    assert accounts.status_code == 200, "the default client should be an admin"

    response = client.post("/admin/users/99999999/role", data={"role": "admin"})

    # 403 for the missing token, and specifically not the 404 the unknown
    # account would otherwise produce — the token is checked first.
    assert response.status_code == 403


# --- the token is scoped to the session that was issued it ------------------


def test_another_users_token_is_rejected(client, sign_in_as, read_csrf_token, slug):
    """A token is only good for the session it was minted for."""
    other = sign_in_as(f"google-oauth2|csrf-{uuid4().hex[:8]}", "grace@example.com", "Grace")
    stolen = read_csrf_token(other)

    response = client.post(
        "/new", data={"slug": slug, "title": "Forged", "body": "x", "csrf_token": stolen}
    )

    assert response.status_code == 403
    assert client.get(f"/pages/{slug}").status_code == 404


def test_the_token_is_stable_within_a_session(client, read_csrf_token):
    """A per-request token would break the back button and duplicate tabs."""
    assert read_csrf_token(client) == read_csrf_token(client)


def test_signing_out_retires_the_token(client, read_csrf_token, sign_in_again, slug):
    """A token minted before sign-out must not survive into the next session."""
    before = read_csrf_token(client)
    client.get("/auth/logout")
    sign_in_again(client)

    response = client.post(
        "/new", data={"slug": slug, "title": "Replayed", "body": "x", "csrf_token": before}
    )

    assert response.status_code == 403
    assert read_csrf_token(client) != before


# --- the JSON API is deliberately untouched ---------------------------------


def test_the_json_api_needs_no_token(client, slug):
    """Requiring one would break every scripted client to close a hole that a
    cross-site form cannot reach — it can't send application/json."""
    response = client.post("/pages", json={"slug": slug, "title": "Scripted", "body": "x"})

    assert response.status_code == 201


@pytest.mark.parametrize(
    "content_type",
    ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data"],
)
def test_json_routes_reject_the_content_types_a_form_can_send(client, slug, content_type):
    """This is the property the exemption above rests on, so it is asserted
    rather than assumed: the three enctypes an HTML form can produce are all
    refused by the JSON body routes."""
    body = f'{{"slug": "{slug}", "title": "Forged", "body": "x"}}'

    response = client.post("/pages", content=body, headers={"Content-Type": content_type})

    assert response.status_code == 422
    assert client.get(f"/pages/{slug}").status_code == 404
