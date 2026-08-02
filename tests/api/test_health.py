"""Contract tests for GET /health.

The canonical test for this project — follow its shape for new surfaces.
"""

from app.version import APP_VERSION, APP_VERSION_NAME, SCHEMA_VERSION


def test_health_reports_the_running_version(client):
    """Happy path: status, body shape, and the fields a client actually reads."""
    response = client.get("/health")

    assert response.status_code == 200

    body = response.json()
    assert set(body) == {"status", "version", "version_name", "schema_version"}
    assert body["status"] == "ok"

    # The whole point of the endpoint: a running container must report the
    # version in the source tree. A mismatch means the rebuild didn't happen.
    assert body["version"] == APP_VERSION
    assert body["version_name"] == APP_VERSION_NAME
    assert body["schema_version"] == SCHEMA_VERSION
    assert isinstance(body["schema_version"], int)


def test_unknown_path_is_404(client):
    """Error path: the app must not serve a catch-all.

    Most likely regression for this surface — a future page router mounted at
    the root would silently swallow unknown paths and mask real 404s.
    """
    response = client.get("/no-such-endpoint")

    assert response.status_code == 404
