"""Contract tests for the edit allowlist and roles.

The Compose environment sets ALLOWED_EMAILS to ada@ and grace@example.com and
ALLOWED_DOMAINS to allowed.example, so anything else signs in as a reader.
"""

from uuid import uuid4

import pytest

HTML = {"accept": "text/html"}


@pytest.fixture
def slug() -> str:
    return f"authz-page-{uuid4().hex[:12]}"


@pytest.fixture
def outsider(client, sign_in_as):
    """A signed-in account that is not on the allowlist.

    Depends on `client` so at least one user already exists — otherwise the
    bootstrap rule would make this account the instance admin.
    """
    return sign_in_as(
        f"google-oauth2|outsider-{uuid4().hex[:8]}", "outsider@nope.example", "Ollie Outsider"
    )


def test_health_reports_the_allowlist_is_configured(anon_client):
    assert anon_client.get("/health").json()["allowlist_configured"] is True


# --- the allowlist ---------------------------------------------------------


def test_an_allowlisted_email_may_write(client, slug):
    assert client.post("/pages", json={"slug": slug, "title": "Allowed"}).status_code == 201


def test_an_allowlisted_domain_may_write(client, sign_in_as, slug):
    insider = sign_in_as("google-oauth2|domain-1", "someone@allowed.example", "Dom Ain")

    assert insider.post("/pages", json={"slug": slug, "title": "By domain"}).status_code == 201


def test_an_outsider_cannot_create(outsider, slug):
    response = outsider.post("/pages", json={"slug": slug, "title": "Nope"})

    assert response.status_code == 403
    assert "edit access" in response.json()["detail"]


def test_an_outsider_cannot_update(client, outsider, slug):
    client.post("/pages", json={"slug": slug, "title": "Mine"})

    response = outsider.put(f"/pages/{slug}", json={"title": "Hijacked"})

    assert response.status_code == 403
    assert client.get(f"/pages/{slug}").json()["title"] == "Mine"


def test_an_outsider_cannot_post_the_edit_form(client, outsider, slug):
    client.post("/pages", json={"slug": slug, "title": "Mine"})

    response = outsider.post(
        f"/w/{slug}/edit", data={"revision": "1", "title": "Hijacked", "body": ""}
    )

    assert response.status_code == 403
    assert client.get(f"/pages/{slug}").json()["title"] == "Mine"


def test_an_outsider_can_still_read_everything(client, outsider, slug):
    client.post("/pages", json={"slug": slug, "title": "Public", "body": "readable"})

    assert outsider.get("/pages").status_code == 200
    assert outsider.get(f"/pages/{slug}").status_code == 200
    assert outsider.get(f"/w/{slug}", headers=HTML).status_code == 200
    assert outsider.get(f"/w/{slug}/history", headers=HTML).status_code == 200


# --- how the refusal is presented ------------------------------------------


def test_a_browser_gets_an_explanatory_403_not_a_login_redirect(outsider, slug):
    """401 says "sign in"; 403 must not, because signing in again won't help."""
    response = outsider.get("/new", headers=HTML)

    assert response.status_code == 403
    assert "You don't have edit access" in response.text
    assert "Ollie Outsider" in response.text
    assert "won't change this" in response.text


def test_an_api_client_gets_json_403(outsider, slug):
    response = outsider.post("/pages", json={"slug": slug, "title": "Nope"})

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/json")


def test_a_reader_sees_no_edit_affordance(client, outsider, slug):
    client.post("/pages", json={"slug": slug, "title": "Look but don't touch"})

    page = outsider.get(f"/w/{slug}", headers=HTML).text
    assert "No edit access" in page
    assert f'href="/w/{slug}/edit"' not in page

    index = outsider.get("/", headers=HTML).text
    assert 'href="/new"' not in index


def test_an_editor_still_sees_the_edit_affordance(client, slug):
    client.post("/pages", json={"slug": slug, "title": "Editable"})

    page = client.get(f"/w/{slug}", headers=HTML).text
    assert f'href="/w/{slug}/edit"' in page
    assert "No edit access" not in page


# --- role assignment -------------------------------------------------------


def test_the_allowlist_is_re_evaluated_on_each_sign_in(sign_in_as, client, slug):
    """A role is not sticky: it follows the allowlist on every sign-in."""
    subject = f"google-oauth2|moving-{uuid4().hex[:8]}"

    off = sign_in_as(subject, "drifter@nope.example", "Drifter")
    assert off.post("/pages", json={"slug": slug, "title": "Nope"}).status_code == 403

    # Same subject, now signing in with an allowlisted address.
    on = sign_in_as(subject, "drifter@allowed.example", "Drifter")
    assert on.post("/pages", json={"slug": slug, "title": "Now allowed"}).status_code == 201


def test_an_outsider_is_not_silently_promoted_by_signing_in_again(outsider, sign_in_as, slug):
    again = sign_in_as("google-oauth2|outsider-persist", "outsider2@nope.example", "Ollie Two")
    assert again.post("/pages", json={"slug": slug, "title": "Nope"}).status_code == 403

    once_more = sign_in_as("google-oauth2|outsider-persist", "outsider2@nope.example", "Ollie Two")
    assert once_more.post("/pages", json={"slug": slug, "title": "Nope"}).status_code == 403
