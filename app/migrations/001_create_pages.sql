-- 001 — the pages table. Bumps SCHEMA_VERSION to 1.
--
-- slug is the stable natural key: every API lookup goes through it, never
-- through the surrogate id.

CREATE TABLE pages (
    id         bigserial   PRIMARY KEY,
    slug       text        NOT NULL UNIQUE,
    title      text        NOT NULL,
    body       text        NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX pages_title_idx ON pages (title);
