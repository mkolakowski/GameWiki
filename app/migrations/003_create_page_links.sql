-- 003 — the wiki-link graph. Bumps SCHEMA_VERSION to 3.
--
-- target_slug is deliberately NOT a foreign key: a page may link to one that
-- doesn't exist yet (a "red link"), and that link should light up on its own
-- the moment someone creates the target.

CREATE TABLE page_links (
    source_id   bigint NOT NULL REFERENCES pages (id) ON DELETE CASCADE,
    target_slug text   NOT NULL,
    PRIMARY KEY (source_id, target_slug)
);

CREATE INDEX page_links_target_idx ON page_links (target_slug);

-- Backfill the graph for pages written before this migration. The slug rules
-- below mirror markup.slugify(); this copy is frozen, so a future change to
-- the Python rules needs its own migration rather than an edit here.
INSERT INTO page_links (source_id, target_slug)
SELECT DISTINCT
    p.id,
    trim(
        both '-' from regexp_replace(lower(split_part(m[1], '|', 1)), '[^a-z0-9]+', '-', 'g')
    )
FROM pages p
CROSS JOIN LATERAL regexp_matches(p.body, '\[\[([^\[\]]+?)\]\]', 'g') AS m
WHERE trim(
    both '-' from regexp_replace(lower(split_part(m[1], '|', 1)), '[^a-z0-9]+', '-', 'g')
) <> ''
ON CONFLICT DO NOTHING;
