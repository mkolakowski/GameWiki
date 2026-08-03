"""Contract tests for the account admin screen.

Compose sets ADMIN_EMAILS=ada@example.com, so the default `client` fixture is
always an admin regardless of what is already in the database. Without that,
"who is admin" would depend on whoever signed in first.
"""

from uuid import uuid4

import pytest

HTML = {"accept": "text/html"}


@pytest.fixture
def admin(client):
    """ada@example.com — admin via ADMIN_EMAILS."""
    return client


@pytest.fixture
def editor(sign_in_as):
    return sign_in_as(f"google-oauth2|ed-{uuid4().hex[:8]}", "grace@example.com", "Grace Hopper")


@pytest.fixture
def reader_name() -> str:
    """Unique per test — _id_of looks accounts up by display name."""
    return f"Reed Er {uuid4().hex[:8]}"


@pytest.fixture
def reader(client, sign_in_as, reader_name):
    """Depends on `client` so this can't be the bootstrap first-ever account."""
    return sign_in_as(
        f"google-oauth2|rd-{uuid4().hex[:8]}",
        f"reader-{uuid4().hex[:8]}@nope.example",
        reader_name,
    )


# --- access ----------------------------------------------------------------


def test_admin_can_see_the_accounts_screen(admin):
    response = admin.get("/admin/users", headers=HTML)

    assert response.status_code == 200
    assert "Accounts" in response.text
    assert "Recent role changes" in response.text


def test_an_editor_cannot(editor):
    response = editor.get("/admin/users", headers=HTML)

    assert response.status_code == 403
    assert "only an admin" in response.text or "edit access" in response.text


def test_a_reader_cannot(reader):
    assert reader.get("/admin/users", headers=HTML).status_code == 403


def test_anonymous_is_sent_to_sign_in(anon_client):
    response = anon_client.get("/admin/users", headers=HTML)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/auth/login?next=")


def test_an_editor_cannot_change_a_role(admin, editor, reader, reader_name):
    target = _id_of(admin, reader_name)

    response = editor.post(f"/admin/users/{target}/role", data={"role": "admin"})

    assert response.status_code == 403
    assert _role_of(admin, target) == "reader"


def test_the_admin_link_only_appears_for_admins(admin, editor):
    assert 'href="/admin/users"' in admin.get("/", headers=HTML).text
    assert 'href="/admin/users"' not in editor.get("/", headers=HTML).text


# --- helpers ---------------------------------------------------------------


def _users(admin) -> list[dict]:
    """Scrape the accounts table — the screen is the contract under test."""
    import html as html_mod
    import re

    html = admin.get("/admin/users", headers=HTML).text
    rows = []
    for block in html.split("<tr>")[1:]:
        ids = re.search(r"/admin/users/(\d+)/role", block)
        selected = re.search(r'<option value="(\w+)" selected', block)
        name = re.search(r"<strong>([^<]*)</strong>", block)
        if ids and selected:
            rows.append(
                {
                    "id": int(ids.group(1)),
                    "role": selected.group(1),
                    "name": html_mod.unescape(name.group(1)) if name else "",
                }
            )
    return rows


def _id_of(admin, name: str) -> int:
    match = next((u for u in _users(admin) if u["name"] == name), None)
    assert match is not None, f"{name} not listed"
    return match["id"]


def _role_of(admin, user_id: int) -> str:
    match = next((u for u in _users(admin) if u["id"] == user_id), None)
    assert match is not None, f"user {user_id} not listed"
    return match["role"]


# --- changing roles --------------------------------------------------------


def test_promoting_a_reader_to_editor(admin, reader, reader_name, form_post):
    target = _id_of(admin, reader_name)
    assert _role_of(admin, target) == "reader"

    response = form_post(
        admin, f"/admin/users/{target}/role", {"role": "editor"}, token_from="/admin/users"
    )

    assert response.status_code == 303
    assert _role_of(admin, target) == "editor"


def test_a_promotion_takes_effect_on_the_next_sign_in(admin, sign_in_as, form_post):
    promo_name = f"Promo Target {uuid4().hex[:8]}"
    subject = f"google-oauth2|promo-{uuid4().hex[:8]}"
    email = f"promo-{uuid4().hex[:8]}@nope.example"
    outsider = sign_in_as(subject, email, promo_name)
    before = outsider.post("/pages", json={"slug": f"p-{uuid4().hex[:8]}", "title": "x"})
    assert before.status_code == 403

    form_post(
        admin,
        f"/admin/users/{_id_of(admin, promo_name)}/role",
        {"role": "editor"},
        token_from="/admin/users",
    )

    # Two things are under test. The old session still carries the old role, so
    # a fresh sign-in is needed; and that sign-in must not let the allowlist
    # undo the promotion, since this address is not on it.
    after = sign_in_as(subject, email, promo_name)
    response = after.post("/pages", json={"slug": f"p-{uuid4().hex[:8]}", "title": "x"})
    assert response.status_code == 201


def test_an_unknown_account_is_404(admin, form_post):
    response = form_post(
        admin, "/admin/users/99999999/role", {"role": "editor"}, token_from="/admin/users"
    )

    assert response.status_code == 404


def test_an_invalid_role_is_rejected(admin, reader, reader_name, form_post):
    target = _id_of(admin, reader_name)

    response = form_post(
        admin, f"/admin/users/{target}/role", {"role": "superuser"}, token_from="/admin/users"
    )

    assert response.status_code == 400
    assert "is not a role" in response.text
    assert _role_of(admin, target) == "reader"


# --- guards ----------------------------------------------------------------


def test_self_demotion_needs_an_explicit_confirmation(admin, sign_in_as, form_post):
    """Losing your own admin rights must never be one careless click."""
    # A second admin, so the last-admin guard isn't what's being tested here.
    name = f"Second Admin {uuid4().hex[:8]}"
    subject = f"google-oauth2|second-{uuid4().hex[:8]}"
    sign_in_as(subject, "second@allowed.example", name)
    me = _id_of(admin, name)
    form_post(admin, f"/admin/users/{me}/role", {"role": "admin"}, token_from="/admin/users")

    # The role is snapshotted into the session, so sign in again to hold it.
    second = sign_in_as(subject, "second@allowed.example", name)
    unconfirmed = form_post(
        second, f"/admin/users/{me}/role", {"role": "editor"}, token_from="/admin/users"
    )

    assert unconfirmed.status_code == 400
    assert "remove your own admin access" in unconfirmed.text
    assert _role_of(admin, me) == "admin"

    confirmed = form_post(
        second,
        f"/admin/users/{me}/role",
        {"role": "editor", "confirm": "yes"},
        token_from="/admin/users",
    )
    assert confirmed.status_code == 303
    assert _role_of(admin, me) == "editor"


def test_the_last_admin_cannot_be_demoted(admin, form_post):
    """An instance with no admin can never hand the role back out."""
    me = next(u for u in _users(admin) if u["name"] == "Ada Lovelace")

    # Reduce to exactly one admin so the guard is the thing under test.
    for account in _users(admin):
        if account["role"] == "admin" and account["id"] != me["id"]:
            form_post(
                admin,
                f"/admin/users/{account['id']}/role",
                {"role": "editor"},
                token_from="/admin/users",
            )

    assert [u["role"] for u in _users(admin)].count("admin") == 1

    response = form_post(
        admin,
        f"/admin/users/{me['id']}/role",
        {"role": "editor", "confirm": "yes"},
        token_from="/admin/users",
    )

    assert response.status_code == 409
    assert "only admin left" in response.text
    assert _role_of(admin, me["id"]) == "admin"


# --- audit -----------------------------------------------------------------


def test_a_role_change_is_recorded_with_who_did_it(admin, reader, reader_name, form_post):
    target = _id_of(admin, reader_name)
    form_post(admin, f"/admin/users/{target}/role", {"role": "editor"}, token_from="/admin/users")

    html = admin.get("/admin/users", headers=HTML).text

    assert "ada@example.com changed" in html
    assert "from reader to editor" in html


def test_the_accounts_screen_escapes_hostile_names(admin, sign_in_as, assert_safe_html, form_post):
    """Display names come from the provider and land in a table and an audit log."""
    hostile = "<img src=x onerror=alert(1)>"
    sign_in_as(
        f"google-oauth2|xss-{uuid4().hex[:8]}",
        "<script>alert(1)</script>@nope.example",
        hostile,
    )
    target = _id_of(admin, hostile)
    form_post(admin, f"/admin/users/{target}/role", {"role": "editor"}, token_from="/admin/users")

    assert_safe_html(admin.get("/admin/users", headers=HTML).text)
