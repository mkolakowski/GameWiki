-- 006 — audit trail for role changes. Bumps SCHEMA_VERSION to 6.
--
-- Emails are denormalised alongside the foreign keys on purpose: an audit
-- record has to stay readable after the account it refers to is deleted, and
-- ON DELETE SET NULL would otherwise leave "someone changed someone's role".

CREATE TABLE role_changes (
    id           bigserial   PRIMARY KEY,
    target_id    bigint      REFERENCES users (id) ON DELETE SET NULL,
    actor_id     bigint      REFERENCES users (id) ON DELETE SET NULL,
    target_label text        NOT NULL,
    actor_label  text        NOT NULL,
    old_role     text        NOT NULL,
    new_role     text        NOT NULL,
    changed_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX role_changes_changed_at_idx ON role_changes (changed_at DESC);

-- Where a role came from. Without this the allowlist recomputation in
-- upsert_user would silently undo every manual promotion at the promoted
-- person's next sign-in — and since anyone on the allowlist is already an
-- editor, the admin screen could only ever demote.
--
-- 'allowlist' roles keep tracking ALLOWED_EMAILS/ALLOWED_DOMAINS, so
-- removing someone still revokes access. 'manual' roles are left alone.
ALTER TABLE users
    ADD COLUMN role_source text NOT NULL DEFAULT 'allowlist'
    CHECK (role_source IN ('allowlist', 'manual'));
