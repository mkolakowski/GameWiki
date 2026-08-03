"""GameWiki version constants — the single source of truth.

Nothing else in the repo carries a hardcoded version string. Anything that
needs the version (health endpoint, in-UI stamp, image label) imports it from
here. See CLAUDE.md for the bump rules.
"""

APP_VERSION = "0.8.0"
"""Semver. Bumped on every commit — PATCH by default."""

APP_VERSION_NAME = "The Guest List"
"""Fun Name for the current release. Must match the top CHANGELOG entry and
the git commit subject. Feeds the version stamp in the page footer."""

SCHEMA_VERSION = 5
"""Incremented by +1 for every DB migration added. Moves independently of
APP_VERSION. Checked against the applied-migration count at startup — a
mismatch is a hard boot failure."""
