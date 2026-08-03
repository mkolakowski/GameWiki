"""Markdown rendering and `[[wiki link]]` resolution.

Page bodies are user-authored, so everything here is written on the assumption
that the input is hostile:

- markdown-it runs with `html=False`, so raw HTML in a body is escaped rather
  than passed through.
- The result is still run through nh3 (ammonia) as defence in depth, which
  strips anything outside a safe tag/attribute allowlist and rejects dangerous
  URL schemes such as `javascript:`.
- Wiki-link display text is escaped before being spliced into markdown source,
  so a crafted label can't break out of the link syntax.

The escaping tests in `tests/unit/test_markup.py` are load-bearing — treat a
failure there as a security regression, not a formatting nit.
"""

import html
import re
from urllib.parse import urlencode

import nh3
from markdown_it import MarkdownIt

# [[Target]] or [[Target|Display text]]
WIKI_LINK_RE = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\[\]|]+?))?\]\]")

_MD = MarkdownIt("commonmark", {"html": False, "linkify": False})

# Characters that would let a crafted label escape the [label](href) syntax.
_MD_SPECIAL_RE = re.compile(r"([\\\[\]()])")


def slugify(text: str) -> str:
    """Fold link text down to a slug matching the API's slug pattern.

    Non-ASCII characters are dropped rather than transliterated, so
    "Pokémon" becomes "pok-mon". Crude, but it keeps slugs inside the
    documented `[a-z0-9-]` alphabet.

    NOTE: migration 003 reimplements this in SQL to backfill existing pages.
    If the rules here change, that backfill is already frozen — write a new
    migration rather than editing it.
    """
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def extract_links(body: str) -> set[str]:
    """Every slug this body links to, including ones that don't exist yet."""
    slugs = {slugify(match.group(1)) for match in WIKI_LINK_RE.finditer(body)}
    slugs.discard("")
    return slugs


def resolve_wiki_links(body: str, existing: set[str]) -> str:
    """Rewrite `[[...]]` into markdown links.

    Links to pages that don't exist point at the create form with the slug and
    title prefilled — the wiki convention of a "red link" that doubles as an
    invitation to write the page. The stylesheet colours them by href prefix.
    """

    def replace(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        label = (match.group(2) or target).strip()
        slug = slugify(target)
        if not slug:
            return match.group(0)

        if slug in existing:
            href = f"/w/{slug}"
        else:
            href = "/new?" + urlencode({"slug": slug, "title": target})

        return f"[{_MD_SPECIAL_RE.sub(r'\\\1', label)}]({href})"

    return WIKI_LINK_RE.sub(replace, body)


def render(body: str, existing: set[str]) -> str:
    """Render a page body to sanitised HTML."""
    return nh3.clean(_MD.render(resolve_wiki_links(body, existing)))


# Repo documentation renders on a different path from wiki pages, for two
# reasons that both bite in practice:
#
# - No `[[link]]` resolution. `resolve_wiki_links` runs over the raw source
#   before markdown parsing, so it rewrites the syntax even inside a code
#   span — and CHANGELOG.md documents that syntax in backticks. Wiki links
#   are a page-authoring feature; a doc has no business gaining them.
# - Tables. The commonmark preset has none, and the guidelines file is mostly
#   tables. `gfm-like` adds them (and strikethrough); linkify stays off to
#   match the page renderer.
#
# Docs are repo files rather than user input, so nh3 has nothing to do here —
# it stays because "trusted" is a property of today's file list, not of this
# function.
_MD_DOC = MarkdownIt("gfm-like", {"html": False, "linkify": False})


def render_document(text: str) -> str:
    """Render a repo document to sanitised HTML."""
    return nh3.clean(_MD_DOC.render(text))


# Sentinels Postgres wraps around search hits in ts_headline output. Control
# characters are used deliberately: asking ts_headline for `<mark>` directly
# would mean receiving raw HTML mixed into a user-authored body with no way
# left to tell the two apart. These survive the round trip and are replaced
# only after the text has been escaped.
HL_START = "\x02"
HL_STOP = "\x03"


def highlight_snippet(snippet: str) -> str:
    """Turn a ts_headline excerpt into safe HTML with the hits marked.

    The excerpt is a slice of a user-authored body, so it is escaped in full
    first and the sentinels are swapped for `<mark>` afterwards — the only
    markup that can reach the browser is markup this function put there.

    nh3 then runs over the result against a `mark`-only allowlist. It cannot
    find anything to strip given the escaping above, but a body containing a
    literal sentinel would otherwise emit an unbalanced tag, and nh3 closes it.
    """
    marked = html.escape(snippet).replace(HL_START, "<mark>").replace(HL_STOP, "</mark>")
    return nh3.clean(marked, tags={"mark"}, attributes={})
