"""GameWiki — FastAPI application entrypoint."""

import os
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app import admin, auth, pages, web
from app.db import pool, run_migrations
from app.version import APP_VERSION, APP_VERSION_NAME, SCHEMA_VERSION


@asynccontextmanager
async def lifespan(_: FastAPI):
    pool.open(wait=True, timeout=30)

    applied = run_migrations()
    if applied != SCHEMA_VERSION:
        raise RuntimeError(
            f"schema drift: {applied} migration(s) applied but SCHEMA_VERSION is "
            f"{SCHEMA_VERSION}. Bump SCHEMA_VERSION by +1 for every migration added."
        )

    yield
    pool.close()


app = FastAPI(title="GameWiki", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=auth.SESSION_SECRET,
    # Lax keeps the session cookie off cross-site POSTs, which is what stands
    # in for CSRF tokens on the edit forms. See the gap noted in CHANGELOG 0.7.0.
    same_site="lax",
    https_only=os.getenv("SESSION_HTTPS_ONLY", "").lower() in {"1", "true", "yes"},
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(admin.router)
app.include_router(web.router)


@app.exception_handler(StarletteHTTPException)
async def unauthorized_goes_to_login(request: Request, exc: StarletteHTTPException):
    """Send browsers to the sign-in page; leave API clients a JSON 401.

    A raw JSON 401 is a dead end for someone who just clicked Edit, but
    redirecting an API client to an HTML login page would be worse.
    """
    wants_html = "text/html" in request.headers.get("accept", "")
    if exc.status_code == 401 and wants_html and auth.is_configured():
        target = quote(request.url.path, safe="/")
        return RedirectResponse(f"/auth/login?next={target}", status_code=303)

    # 403 is a different answer from 401: signing in again would not help,
    # so the page explains that rather than bouncing to the provider.
    if exc.status_code == 403 and wants_html:
        return web.render_forbidden(request, exc.detail)

    return await http_exception_handler(request, exc)


@app.get("/health")
def health() -> dict[str, str | int | bool]:
    """Report liveness and the running version.

    The rebuild rule polls this after every version bump — if it reports a
    stale APP_VERSION, the container is running old code.
    """
    return {
        "status": "ok",
        "version": APP_VERSION,
        "version_name": APP_VERSION_NAME,
        "schema_version": SCHEMA_VERSION,
        "auth_configured": auth.is_configured(),
        "allowlist_configured": auth.allowlist_is_configured(),
    }
