#!/usr/bin/env python3
"""Assert the release metadata is internally consistent.

CLAUDE.md states four rules that are easy to forget and invisible in review:
every commit bumps the version, the changelog's top entry matches it, the Fun
Name matches everywhere, and SCHEMA_VERSION equals the migration count. This
checks all four so CI can fail on them instead of a reader noticing later.

    python3 scripts/check_release.py              # consistency only
    python3 scripts/check_release.py --base main  # also require a bump vs main
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "app" / "version.py"
CHANGELOG = ROOT / "CHANGELOG.md"
MIGRATIONS = ROOT / "app" / "migrations"

ENTRY_RE = re.compile(
    r'^## \[(?P<version>\d+\.\d+\.\d+)\] - (?P<date>\d{4}-\d{2}-\d{2}) [—-] "(?P<name>[^"]+)"',
    re.MULTILINE,
)


def read_constant(text: str, name: str) -> str:
    match = re.search(rf'^{name} = "(?P<value>[^"]+)"', text, re.MULTILINE)
    if match is None:
        raise SystemExit(f"could not find {name} in {VERSION_FILE.name}")
    return match.group("value")


def read_int_constant(text: str, name: str) -> int:
    match = re.search(rf"^{name} = (?P<value>\d+)", text, re.MULTILINE)
    if match is None:
        raise SystemExit(f"could not find {name} in {VERSION_FILE.name}")
    return int(match.group("value"))


def version_at(ref: str) -> str | None:
    """APP_VERSION as of a git ref, or None if the file didn't exist there."""
    result = subprocess.run(
        ["git", "show", f"{ref}:app/version.py"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        return None
    return read_constant(result.stdout, "APP_VERSION")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        help="git ref to compare against; the version must differ from it",
    )
    args = parser.parse_args()

    source = VERSION_FILE.read_text()
    app_version = read_constant(source, "APP_VERSION")
    app_version_name = read_constant(source, "APP_VERSION_NAME")
    schema_version = read_int_constant(source, "SCHEMA_VERSION")

    failures: list[str] = []

    entry = ENTRY_RE.search(CHANGELOG.read_text())
    if entry is None:
        failures.append("CHANGELOG.md has no parseable release entry")
    else:
        if entry.group("version") != app_version:
            failures.append(
                f"changelog's top entry is {entry.group('version')} but APP_VERSION is "
                f"{app_version} — every bump needs its own entry at the top"
            )
        if entry.group("name") != app_version_name:
            failures.append(
                f"changelog's top entry is named {entry.group('name')!r} but "
                f"APP_VERSION_NAME is {app_version_name!r} — they must match"
            )

    migration_count = len(list(MIGRATIONS.glob("*.sql")))
    if migration_count != schema_version:
        failures.append(
            f"SCHEMA_VERSION is {schema_version} but there are {migration_count} "
            "migration(s) — bump it by +1 for every migration added"
        )

    if args.base:
        base_version = version_at(args.base)
        if base_version is None:
            print(f"note: no app/version.py at {args.base}; skipping the bump check")
        elif base_version == app_version:
            failures.append(
                f"APP_VERSION is still {app_version} at {args.base} — every commit "
                "ships its own version bump"
            )

    if failures:
        print("release check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(f'release check passed: {app_version} — "{app_version_name}", schema {schema_version}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
