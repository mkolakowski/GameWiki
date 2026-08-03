"""Unit tests for markdown rendering and wiki-link resolution.

The escaping tests here are load-bearing: page bodies are user-authored, so a
failure in this file is a stored-XSS regression, not a formatting nit.
"""

import pytest

from app import markup


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Chrono Trigger", "chrono-trigger"),
        ("  Outer Wilds  ", "outer-wilds"),
        ("ALL CAPS", "all-caps"),
        ("Half-Life 2", "half-life-2"),
        ("Zelda: Ocarina of Time", "zelda-ocarina-of-time"),
        ("Pokémon", "pok-mon"),  # non-ASCII is dropped, not transliterated
        ("---", ""),
        ("", ""),
    ],
)
def test_slugify(text, expected):
    assert markup.slugify(text) == expected


def test_extract_links_finds_targets_and_ignores_aliases():
    body = "See [[Chrono Trigger]] and [[Outer Wilds|that space game]]."

    assert markup.extract_links(body) == {"chrono-trigger", "outer-wilds"}


def test_extract_links_on_a_body_with_none():
    assert markup.extract_links("Just prose. [not a wiki link](/w/x)") == set()


def test_existing_target_links_to_the_page():
    html = markup.render("See [[Chrono Trigger]].", {"chrono-trigger"})

    # nh3 appends rel="noopener noreferrer" to anchors, so match on the parts
    # that matter rather than the whole tag.
    assert 'href="/w/chrono-trigger"' in html
    assert ">Chrono Trigger</a>" in html


def test_missing_target_becomes_a_red_link_to_the_create_form():
    html = markup.render("See [[Chrono Trigger]].", set())

    # Prefilled so the red link doubles as an invitation to write the page.
    assert 'href="/new?slug=chrono-trigger&amp;title=Chrono+Trigger"' in html
    assert ">Chrono Trigger</a>" in html


def test_alias_changes_the_link_text_only():
    html = markup.render("[[Outer Wilds|that space game]]", {"outer-wilds"})

    assert 'href="/w/outer-wilds"' in html
    assert ">that space game</a>" in html


def test_markdown_is_rendered():
    html = markup.render("# Heading\n\nSome **bold** text.\n\n- one\n- two", set())

    assert "<h1>Heading</h1>" in html
    assert "<strong>bold</strong>" in html
    assert "<li>one</li>" in html


# --- escaping: these must not regress -------------------------------------
#
# Asserted structurally via assert_safe_html, which parses the output. A
# substring check can't distinguish `<script>` from `&lt;script&gt;`, so it
# would fail on safely-escaped text and pass on markup hidden in an attribute.

HOSTILE_BODIES = [
    "<script>alert(1)</script>",
    '<img src=x onerror="alert(1)">',
    '<iframe src="https://evil.example"></iframe>',
    "[click me](javascript:alert1)",
    "[click me](JaVaScRiPt:alert1)",
    "[click me](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)",
    "<svg/onload=alert(1)>",
    '<a href="javascript:alert(1)">x</a>',
    "<style>body{display:none}</style>",
    # Crafted wiki links: labels and targets carrying markdown or HTML syntax.
    "[[Real Page|](javascript:alert1)]]",
    '[[Page" onmouseover="alert(1)]]',
    "[[Real Page|<script>alert(1)</script>]]",
    "[[<img src=x onerror=alert(1)>]]",
]


@pytest.mark.parametrize("body", HOSTILE_BODIES)
def test_hostile_body_renders_no_dangerous_markup(body, assert_safe_html):
    assert_safe_html(markup.render(body, {"real-page"}))


def test_raw_html_is_escaped_rather_than_dropped():
    """The text should survive as visible text — just not as markup."""
    html = markup.render("<script>alert(1)</script>", set())

    assert "&lt;script&gt;" in html


def test_a_javascript_link_is_not_an_anchor_at_all():
    html = markup.render("[click me](javascript:alert1)", set())

    assert "<a " not in html
