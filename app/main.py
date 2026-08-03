"""GameWiki — FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import pages, web
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
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(pages.router)
app.include_router(web.router)


@app.get("/health")
def health() -> dict[str, str | int]:
    """Report liveness and the running version.

    The rebuild rule polls this after every version bump — if it reports a
    stale APP_VERSION, the container is running old code.
    """
    return {
        "status": "ok",
        "version": APP_VERSION,
        "version_name": APP_VERSION_NAME,
        "schema_version": SCHEMA_VERSION,
    }
