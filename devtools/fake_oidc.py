"""A minimal OpenID Connect provider for local development and CI.

CLAUDE.md requires external APIs to be Compose services rather than public
endpoints called at request time. Google's OIDC endpoints obviously can't be
self-hosted, so this stands in for them: it speaks enough real OIDC —
discovery, JWKS, authorization code exchange, and an RS256-signed id_token —
that the app under test runs its genuine Authlib code path rather than a
bypass.

It is NOT a security product and must never be deployed. It approves every
authorization request without asking anyone anything, and it accepts any
client secret. That is the point: tests need a provider that always says yes.

**Limitation worth remembering:** passing against this stub does not prove the
app works against Google. The stub is deliberately permissive, so a bug where
the app skips a check Google enforces would go unnoticed here. Real-Google
verification is manual.

Tests choose who logs in by POSTing to `/_test/identity` first.
"""

import time
import uuid
from typing import Any

from authlib.jose import JsonWebKey, jwt
from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

ISSUER = "http://oidc:9000"
KID = "fake-oidc-key"


def _new_key():
    return JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": KID})


# Regenerated on every restart, and on demand via /_test/rotate_key. Both
# simulate a provider rotating its signing keys, which a relying party with a
# cached JWK set has to survive.
_KEY = _new_key()

# The identity the next login will produce. Mutable so tests can log in as
# more than one person.
_identity: dict[str, str] = {
    "sub": "google-oauth2|000000000000000000001",
    "email": "ada@example.com",
    "name": "Ada Lovelace",
}

# code -> pending authorization
_codes: dict[str, dict[str, Any]] = {}

app = FastAPI(title="fake-oidc", docs_url=None, redoc_url=None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/_test/identity")
async def set_identity(request: Request) -> dict[str, str]:
    """Choose the identity the next authorization will issue."""
    payload = await request.json()
    _identity.update({k: str(v) for k, v in payload.items() if k in {"sub", "email", "name"}})
    return dict(_identity)


@app.post("/_test/rotate_key")
def rotate_key() -> dict[str, str]:
    """Rotate the signing key, invalidating any cached JWK set."""
    global _KEY
    _KEY = _new_key()
    return {"status": "rotated"}


@app.get("/.well-known/openid-configuration")
def discovery() -> dict[str, Any]:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "userinfo_endpoint": f"{ISSUER}/userinfo",
        "jwks_uri": f"{ISSUER}/jwks.json",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "email", "profile"],
        "grant_types_supported": ["authorization_code"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
        ],
    }


@app.get("/jwks.json")
def jwks() -> dict[str, Any]:
    public = _KEY.as_dict(is_private=False)
    public.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return {"keys": [public]}


@app.get("/authorize")
def authorize(
    redirect_uri: str,
    state: str = "",
    nonce: str = "",
    client_id: str = "",
    scope: str = "",
    response_type: str = "code",
) -> RedirectResponse:
    """Approve immediately — no login screen, no consent."""
    code = uuid.uuid4().hex
    _codes[code] = {
        "nonce": nonce,
        "client_id": client_id,
        "identity": dict(_identity),
    }

    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{separator}code={code}&state={state}", status_code=302)


@app.post("/token")
def token(
    code: str = Form(...),
    client_id: str = Form(default=""),
    grant_type: str = Form(default="authorization_code"),
    redirect_uri: str = Form(default=""),
) -> JSONResponse:
    pending = _codes.pop(code, None)
    if pending is None:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    identity = pending["identity"]
    audience = pending["client_id"] or client_id
    now = int(time.time())

    claims = {
        "iss": ISSUER,
        "aud": audience,
        "sub": identity["sub"],
        "email": identity["email"],
        "email_verified": True,
        "name": identity["name"],
        "iat": now,
        "exp": now + 3600,
    }
    if pending["nonce"]:
        claims["nonce"] = pending["nonce"]

    id_token = jwt.encode({"alg": "RS256", "kid": KID}, claims, _KEY).decode()

    return JSONResponse(
        {
            "access_token": uuid.uuid4().hex,
            "id_token": id_token,
            "token_type": "Bearer",
            "expires_in": 3600,
        }
    )


@app.get("/userinfo")
def userinfo() -> dict[str, Any]:
    return {
        "sub": _identity["sub"],
        "email": _identity["email"],
        "email_verified": True,
        "name": _identity["name"],
    }
