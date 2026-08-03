"""Role changes take effect immediately, without the affected user signing out.

Until 0.13.0 the role was snapshotted into the session at sign-in, so a demoted
user kept writing until their session ended. That is the failure mode these
tests exist for: revoking access has to actually revoke access, on the next
request, not whenever the person happens to sign in again.

Every test here drives an *existing, already-signed-in* client. Re-signing in
would test the old path and pass either way.
"""

import re
from uuid import uuid4

import pytest

HTML = {"accept": "text/html"}


@pytest.fixture
def admin(client):
    """ada@example.com — admin via ADMIN_EMAILS in the Compose config."""
    return client


@pytest.fixture
def victim_name() -> str:
    return f"Live Role {uuid4().hex[:8]}"


@pytest.fixture
def victim(admin, sign_in_as, victim_name):
    """A signed-in account whose role the tests move underneath it.

    Depends on `admin` so this can never be the bootstrap first-ever account.
    """
    return sign_in_as(
        f"google-oauth2|live-{uuid4().hex[:8]}",
        f"live-{uuid4().hex[:8]}@nope.example",
        victim_name,
    )


def _id_of(admin, name: str) -> int:
    """Look the account up by display name, per row.

    Parsed a row at a time rather than by scanning the whole page: the id lives
    in the form action, which comes *after* the name in the row, so any
    whole-page search finds the neighbouring account's id instead.
    """
    html = admin.get("/admin/users", headers=HTML).text
    for block in html.split("<tr>")[1:]:
        row_name = re.search(r"<strong>([^<]*)</strong>", block)
        row_id = re.search(r"/admin/users/(\d+)/role", block)
        if row_name and row_id and row_name.group(1) == name:
            return int(row_id.group(1))
    raise AssertionError(f"{name} not listed")


def _set_role(admin, form_post, user_id: int, role: str) -> None:
    response = form_post(
        admin, f"/admin/users/{user_id}/role", {"role": role}, token_from="/admin/users"
    )
    assert response.status_code == 303, response.text


def _write(client) -> int:
    """Attempt a write on the JSON API, returning the status code."""
    return client.post("/pages", json={"slug": f"live-{uuid4().hex[:8]}", "title": "x"}).status_code


# --- the gap this release closes --------------------------------------------


def test_a_promotion_applies_without_signing_in_again(admin, victim, victim_name, form_post):
    assert _write(victim) == 403

    _set_role(admin, form_post, _id_of(admin, victim_name), "editor")

    # Same client, same cookie, no re-authentication.
    assert _write(victim) == 201


def test_a_demotion_applies_without_signing_out(admin, victim, victim_name, form_post):
    """The security-relevant direction: revoking must actually revoke."""
    target = _id_of(admin, victim_name)
    _set_role(admin, form_post, target, "editor")
    assert _write(victim) == 201

    _set_role(admin, form_post, target, "reader")

    assert _write(victim) == 403


def test_a_demotion_closes_the_html_write_path_too(admin, victim, victim_name, form_post):
    """Both surfaces read the same live role, not just the JSON one."""
    target = _id_of(admin, victim_name)
    _set_role(admin, form_post, target, "editor")
    assert victim.get("/new", headers=HTML).status_code == 200

    _set_role(admin, form_post, target, "reader")

    assert victim.get("/new", headers=HTML).status_code == 403


def test_a_demoted_admin_loses_the_accounts_screen(admin, sign_in_as, form_post):
    name = f"Temp Admin {uuid4().hex[:8]}"
    subject = f"google-oauth2|tmp-{uuid4().hex[:8]}"
    second = sign_in_as(subject, "second@allowed.example", name)
    target = _id_of(admin, name)

    _set_role(admin, form_post, target, "admin")
    assert second.get("/admin/users", headers=HTML).status_code == 200

    _set_role(admin, form_post, target, "editor")

    assert second.get("/admin/users", headers=HTML).status_code == 403


def test_demoting_yourself_takes_effect_immediately(admin, sign_in_as, form_post):
    """The actor's own session must not keep a stale admin cookie either."""
    name = f"Self Demote {uuid4().hex[:8]}"
    subject = f"google-oauth2|self-{uuid4().hex[:8]}"
    second = sign_in_as(subject, "second@allowed.example", name)
    me = _id_of(admin, name)
    _set_role(admin, form_post, me, "admin")
    assert second.get("/admin/users", headers=HTML).status_code == 200

    response = form_post(
        second,
        f"/admin/users/{me}/role",
        {"role": "editor", "confirm": "yes"},
        token_from="/admin/users",
    )
    assert response.status_code == 303

    assert second.get("/admin/users", headers=HTML).status_code == 403


# --- what the user is shown -------------------------------------------------


def test_the_nav_reflects_the_new_role_immediately(admin, victim, victim_name, form_post):
    """A reader must stop being offered a New page link that would only 403."""
    target = _id_of(admin, victim_name)
    _set_role(admin, form_post, target, "editor")
    assert 'href="/new"' in victim.get("/", headers=HTML).text

    _set_role(admin, form_post, target, "reader")

    assert 'href="/new"' not in victim.get("/", headers=HTML).text


# --- reads stay anonymous and cheap -----------------------------------------


def test_anonymous_reads_still_work(anon_client):
    """The live lookup must not accidentally require a session."""
    assert anon_client.get("/", headers=HTML).status_code == 200
    assert anon_client.get("/pages").status_code == 200
