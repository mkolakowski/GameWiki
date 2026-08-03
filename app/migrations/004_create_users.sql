-- 004 — OIDC users and revision authorship. Bumps SCHEMA_VERSION to 4.
--
-- No password column by design: identity comes from an OIDC provider, so this
-- app never sees or stores a credential. (issuer, subject) is the identity —
-- `sub` is only unique within an issuer, and email is not stable enough to key
-- on since a Google account can change address.

CREATE TABLE users (
    id           bigserial   PRIMARY KEY,
    issuer       text        NOT NULL,
    subject      text        NOT NULL,
    email        text,
    name         text        NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (issuer, subject)
);

-- Nullable, and ON DELETE SET NULL: revisions written before this migration
-- have no author, and deleting a user must not delete the wiki's history.
ALTER TABLE page_revisions
    ADD COLUMN author_id bigint REFERENCES users (id) ON DELETE SET NULL;

CREATE INDEX page_revisions_author_idx ON page_revisions (author_id);
