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


def _csv_set(name: str) -> set[str]:
    return {
        item.strip().lower().lstrip("@") for item in os.getenv(name, "").split(",") if item.strip()
    }


# Who may edit. Both empty means the wiki is open to any account that can
# sign in — the 0.7.0 behaviour, kept so an upgrade does not lock everyone
# out, but reported by /health so it is not a silent default.
ALLOWED_EMAILS = _csv_set("ALLOWED_EMAILS")
ALLOWED_DOMAINS = _csv_set("ALLOWED_DOMAINS")

# Accounts that are always admin. This is how an instance bootstraps one
# deliberately, rather than relying on whoever happened to sign in first —
# which on a public instance could be a passer-by.
ADMIN_EMAILS = _csv_set("ADMIN_EMAILS")

EDITOR_ROLES = {"editor", "admin"}

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


def allowlist_is_configured() -> bool:
    return bool(ALLOWED_EMAILS or ALLOWED_DOMAINS)


def email_is_admin(email: str | None) -> bool:
    return bool(email) and email.lower() in ADMIN_EMAILS


def email_is_allowed(email: str | None) -> bool:
    """Whether this address earns the editor role at sign-in."""
    if not allowlist_is_configured():
        return True
    if not email:
        return False

    email = email.lower()
    return email in ALLOWED_EMAILS or email.rpartition("@")[2] in ALLOWED_DOMAINS


def current_user(request: Request) -> dict | None:
    """The signed-in user, or None. Never raises — reads are anonymous."""
    return request.session.get("user")


def require_user(request: Request) -> dict:
    """The signed-in user, or a 401. Authentication only."""
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


def require_editor(request: Request) -> dict:
    """A signed-in user who may write, or 401/403.

    401 and 403 are different answers: 401 means "we don't know who you are,
    sign in", 403 means "we know exactly who you are and the answer is no".
    Signing in again would not help the second case.
    """
    user = require_user(request)
    if user.get("role") not in EDITOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="your account does not have edit access on this wiki",
        )
    return user


def require_admin(request: Request) -> dict:
    """A signed-in admin, or 401/403."""
    user = require_user(request)
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only an admin can manage accounts on this wiki",
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

    email = claims.get("email")
    user = repo.upsert_user(
        issuer=claims.get("iss", OIDC_DISCOVERY_URL),
        subject=subject,
        email=email,
        name=claims.get("name") or email or "Anonymous",
        allowed=email_is_allowed(email),
        is_admin=email_is_admin(email),
    )

    # The role is snapshotted into the session, so a role change made in the
    # database takes effect on the user's next sign-in, not immediately.
    request.session["user"] = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
    }

    return RedirectResponse(request.session.pop("next", "/"), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/logout")
def logout(request: Request):
    """Clears the local session only — the Google session is untouched."""
    request.session.pop("user", None)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
