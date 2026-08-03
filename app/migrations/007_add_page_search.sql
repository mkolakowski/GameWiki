-- 007 — full-text search over page titles and bodies. Bumps SCHEMA_VERSION to 7.
--
-- search_vector is a GENERATED column rather than a trigger-maintained one, so
-- there is nothing for the repository layer to remember and no way for the
-- index to drift out of step with the row. It also backfills every existing
-- page on ALTER, which is why this migration has no separate backfill step.
--
-- The two-argument to_tsvector(regconfig, text) is IMMUTABLE, which a generated
-- column requires; the one-argument form reads default_text_search_config and
-- is only STABLE, so naming 'english' explicitly here is load-bearing rather
-- than stylistic.
--
-- Titles are weighted 'A' and bodies 'B', so a page *named* for the search term
-- outranks one that merely mentions it in passing.

ALTER TABLE pages
    ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english'::regconfig, coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english'::regconfig, coalesce(body, '')), 'B')
    ) STORED;

CREATE INDEX pages_search_idx ON pages USING gin (search_vector);
