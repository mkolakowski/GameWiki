-- 005 — user roles. Bumps SCHEMA_VERSION to 5.
--
-- reader: can read, cannot write (the default for anyone off the allowlist)
-- editor: can create and edit pages
-- admin:  editor, and never demoted by an allowlist change
--
-- The role is re-evaluated from the allowlist on every sign-in, so removing
-- someone from ALLOWED_EMAILS actually takes their access away. Admins are the
-- exception — otherwise an operator could lock themselves out by editing an
-- env var.

ALTER TABLE users
    ADD COLUMN role text NOT NULL DEFAULT 'reader'
    CHECK (role IN ('reader', 'editor', 'admin'));

-- An instance upgrading from 0.7.0 already has accounts and would otherwise
-- have no admin at all. Promote the earliest one.
UPDATE users
SET role = 'admin'
WHERE id = (SELECT id FROM users ORDER BY created_at, id LIMIT 1);
