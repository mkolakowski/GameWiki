"""Google OIDC sign-in.

The app is provider-agnostic — it reads a discovery URL from the environment
and defaults to Google. Local development and CI point it at the stub provider
in `devtools/fake_oidc.py`, running as the `oidc` Compose service, so the real
Authlib code path is exercised without reaching the public internet.

Reads are anonymous. Writes require a signed-in user. If OIDC is not
configured, the app still boots and serves reads, but writes are refused —
failing closed rather than silently reverting to anonymous editing.
"""

import os
import secrets

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app import repository as repo

try:  # Authlib >= 1.6 delegates JOSE to joserfc.
    from joserfc.errors import JoseError
except ImportError:  # pragma: no cover - older Authlib bundles its own.
    from authlib.jose.errors import JoseError

GOOGLE_DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"

OIDC_DISCOVERY_URL = os.getenv("OIDC_DISCOVERY_URL", GOOGLE_DISCOVERY)
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")

# Sessions survive a restart only if this is set explicitly. An ephemeral
# secret keeps the app bootable without config; it just signs everyone out.
SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_urlsafe(32)

router = APIRouter(prefix="/auth", tags=["auth"])

oauth = OAuth()

if OIDC_CLIENT_ID and OIDC_CLIENT_SECRET:
    oauth.register(
        name="oidc",
        server_metadata_url=OIDC_DISCOVERY_URL,
        client_id=OIDC_CLIENT_ID,
        client_secret=OIDC_CLIENT_SECRET,
        client_kwargs={"scope": "openid email profile"},
    )


def is_configured() -> bool:
    return bool(OIDC_CLIENT_ID and OIDC_CLIENT_SECRET)


def current_user(request: Request) -> dict | None:
    """The signed-in user, or None. Never raises — reads are anonymous."""
    return request.session.get("user")


def require_user(request: Request) -> dict:
    """The signed-in user, or a 401. Use on every write path."""
    user = current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "sign in to edit"
                if is_configured()
                else "editing is disabled: this instance has no OIDC provider configured"
            ),
        )
    return user


@router.get("/login")
async def login(request: Request, next: str = "/"):
    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="no OIDC provider configured",
        )

    # Only same-site paths, so a crafted ?next= can't bounce a signed-in user
    # off to another origin.
    request.session["next"] = next if next.startswith("/") and not next.startswith("//") else "/"

    return await oauth.oidc.authorize_redirect(request, str(request.url_for("auth_callback")))


@router.get("/callback", name="auth_callback")
async def callback(request: Request):
    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="no OIDC provider configured",
        )

    try:
        token = await oauth.oidc.authorize_access_token(request)
    except JoseError:
        # The id_token didn't verify against our cached JWK set. Providers
        # rotate signing keys — Google does so routinely — and Authlib caches
        # the key set on the client indefinitely, so a rotation turns every
        # sign-in into a 500 until the process restarts.
        #
        # The authorization code is already spent by this point, so this
        # attempt can't be salvaged. Drop the stale cache instead, which makes
        # the next attempt succeed, and tell the user to try again rather than
        # showing them a traceback.
        await oauth.oidc.fetch_jwk_set(force=True)
        return HTMLResponse(
            "<h1>Sign-in failed</h1>"
            "<p>The provider's signing keys changed. "
            '<a href="/auth/login">Try again</a>.</p>',
            status_code=400,
        )
    except OAuthError as error:
        return HTMLResponse(f"<h1>Sign-in failed</h1><p>{error.error}</p>", status_code=400)

    claims = token.get("userinfo") or {}
    subject = claims.get("sub")
    if not subject:
        return HTMLResponse("<h1>Sign-in failed</h1><p>no subject claim</p>", status_code=400)

    user = repo.upsert_user(
        issuer=claims.get("iss", OIDC_DISCOVERY_URL),
        subject=subject,
        email=claims.get("email"),
        name=claims.get("name") or claims.get("email") or "Anonymous",
    )

    request.session["user"] = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
    }

    return RedirectResponse(request.session.pop("next", "/"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/logout")
def logout(request: Request):
    """Clears the local session only — the Google session is untouched."""
    request.session.pop("user", None)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
