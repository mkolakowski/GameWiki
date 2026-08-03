-- 002 — revision history. Bumps SCHEMA_VERSION to 2.
--
-- Every version of a page is a row here, including the original: a page
-- created and never edited has exactly one revision. pages.revision is a
-- denormalised pointer at the latest one, and doubles as the ETag for
-- optimistic concurrency on PUT.

ALTER TABLE pages ADD COLUMN revision integer NOT NULL DEFAULT 1;

CREATE TABLE page_revisions (
    id         bigserial   PRIMARY KEY,
    page_id    bigint      NOT NULL REFERENCES pages (id) ON DELETE CASCADE,
    revision   integer     NOT NULL,
    title      text        NOT NULL,
    body       text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (page_id, revision)
);

CREATE INDEX page_revisions_page_idx ON page_revisions (page_id, revision DESC);

-- Pages that predate this migration become their own revision 1, so no page
-- is left with an empty history.
INSERT INTO page_revisions (page_id, revision, title, body, created_at)
SELECT id, 1, title, body, updated_at FROM pages;
