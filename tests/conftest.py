"""Shared fixtures for the integration suite.

These tests talk to the **running** app over the network, not to in-process
code — so a stale container fails them. Rebuild before running:

    docker compose up -d --build app
    docker compose exec app pytest -q
"""

import os
import re
from html.parser import HTMLParser

import httpx
import pytest

CSRF_FIELD_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def csrf_token(client: httpx.Client, path: str = "/new") -> str:
    """This session's CSRF token, scraped from a rendered form.

    A browser reads this out of the hidden field, so the suite does too rather
    than reaching into the signed session cookie — that way a template which
    forgets the field breaks the tests that depend on it.
    """
    response = client.get(path)
    match = CSRF_FIELD_RE.search(response.text)
    assert match, f"no csrf_token field at {path} (HTTP {response.status_code})"
    return match.group(1)


# Tags that should never appear in rendered page content. `form`, `meta`, and
# `link` are omitted deliberately — the app's own chrome uses them.
DANGEROUS_TAGS = {"script", "iframe", "object", "embed", "style", "base"}
DANGEROUS_SCHEMES = ("javascript:", "vbscript:", "data:")
URL_ATTRS = {"href", "src", "action", "formaction", "xlink:href"}


class _ElementCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_startendtag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def audit_html(html: str) -> list[str]:
    """Structural check for injected markup.

    Substring assertions can't tell `<script>` from `&lt;script&gt;` — escaped
    text reads as a failure and live markup inside an attribute reads as a
    pass. This parses instead, and reports actual dangerous elements.
    """
    collector = _ElementCollector()
    collector.feed(html)

    problems = []
    for tag, attrs in collector.elements:
        if tag in DANGEROUS_TAGS:
            problems.append(f"<{tag}>")
        for name, value in attrs.items():
            if name.lower().startswith("on"):
                problems.append(f"<{tag} {name}=...>")
            if name.lower() in URL_ATTRS and value:
                scheme = "".join(value.split()).lower()
                if scheme.startswith(DANGEROUS_SCHEMES):
                    problems.append(f"<{tag} {name}={value!r}>")
    return problems


@pytest.fixture
def assert_safe_html():
    def check(html: str) -> None:
        problems = audit_html(html)
        assert not problems, f"unsafe markup rendered: {problems}\n{html}"

    return check


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.getenv("GAMEWIKI_BASE_URL", "http://localhost:8000").rstrip("/")


@pytest.fixture(scope="session")
def oidc_base_url() -> str:
    """The stub provider — see devtools/fake_oidc.py."""
    return os.getenv("OIDC_TEST_BASE_URL", "http://oidc:9000").rstrip("/")


def sign_in(
    client: httpx.Client,
    oidc_base_url: str,
    *,
    sub: str = "google-oauth2|000000000000000000001",
    email: str = "ada@example.com",
    name: str = "Ada Lovelace",
) -> None:
    """Drive a real authorization-code flow against the stub provider.

    Nothing here is mocked: the app performs discovery, redirects, exchanges
    the code, and validates an RS256 id_token. The stub just always says yes.
    """
    httpx.post(
        f"{oidc_base_url}/_test/identity",
        json={"sub": sub, "email": email, "name": name},
        timeout=10.0,
    ).raise_for_status()

    response = client.get("/auth/login", params={"next": "/"}, follow_redirects=True)
    assert response.status_code == 200, f"sign-in failed: {response.status_code} {response.text}"


@pytest.fixture
def read_csrf_token():
    """Scrape a client's current token, the way a browser reads the field."""
    return csrf_token


@pytest.fixture
def sign_in_again(oidc_base_url: str):
    """Re-authenticate an existing client, for session-boundary tests."""

    def again(client: httpx.Client, **kwargs) -> None:
        sign_in(client, oidc_base_url, **kwargs)

    return again


@pytest.fixture
def form_post():
    """Submit an HTML form the way a browser would, hidden token included.

    Routes that refuse before the token is even looked at — anonymous or
    non-editor callers — are posted to directly in the tests instead, since
    attaching a token there would test nothing.
    """

    def post(client: httpx.Client, url: str, data: dict, *, token_from: str = "/new"):
        payload = {**data}
        payload.setdefault("csrf_token", csrf_token(client, token_from))
        return client.post(url, data=payload)

    return post


@pytest.fixture
def anon_client(base_url: str):
    """A client that has not signed in."""
    with httpx.Client(base_url=base_url, timeout=10.0) as c:
        yield c


@pytest.fixture
def client(base_url: str, oidc_base_url: str):
    """A signed-in client. Most of the suite writes, so this is the default."""
    with httpx.Client(base_url=base_url, timeout=10.0) as c:
        sign_in(c, oidc_base_url)
        yield c


@pytest.fixture
def sign_in_as(base_url: str, oidc_base_url: str):
    """Build an additional signed-in client, for multi-user tests."""
    clients = []

    def make(sub: str, email: str, name: str) -> httpx.Client:
        c = httpx.Client(base_url=base_url, timeout=10.0)
        sign_in(c, oidc_base_url, sub=sub, email=email, name=name)
        clients.append(c)
        return c

    yield make

    for c in clients:
        c.close()
