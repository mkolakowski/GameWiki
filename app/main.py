"""GameWiki — FastAPI application entrypoint."""

from fastapi import FastAPI

from app.version import APP_VERSION, APP_VERSION_NAME, SCHEMA_VERSION

app = FastAPI(title="GameWiki", version=APP_VERSION)


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
