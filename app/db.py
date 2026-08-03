"""Database connection pool and the migration runner.

Migrations run once at process start (see the lifespan hook in `app.main`),
which is why a SCHEMA_VERSION bump requires a rebuild to take effect.
"""

import os
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://gamewiki:gamewiki@localhost:5432/gamewiki")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=5,
    kwargs={"row_factory": dict_row},
    open=False,
)


def run_migrations() -> int:
    """Apply every unapplied migration in filename order.

    Returns the total number of applied migrations, which the caller checks
    against SCHEMA_VERSION — a mismatch means the constant and the migrations
    directory have drifted apart.
    """
    with pool.connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  name text PRIMARY KEY,"
            "  applied_at timestamptz NOT NULL DEFAULT now()"
            ")"
        )
        rows = conn.execute("SELECT name FROM schema_migrations").fetchall()
        applied = {row["name"] for row in rows}

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))

        total = conn.execute("SELECT count(*) AS n FROM schema_migrations").fetchone()
        return total["n"]
