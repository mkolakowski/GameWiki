"""Shared fixtures for the integration suite.

These tests talk to the **running** app over the network, not to in-process
code — so a stale container fails them. Rebuild before running:

    docker compose up -d --build app
    docker compose exec app pytest -q
"""

import os

import httpx
import pytest


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.getenv("GAMEWIKI_BASE_URL", "http://localhost:8000").rstrip("/")


@pytest.fixture
def client(base_url: str):
    with httpx.Client(base_url=base_url, timeout=10.0) as c:
        yield c
