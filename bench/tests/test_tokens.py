# SPDX-License-Identifier: GPL-2.0-or-later
"""Colour tokens in bench/static/style.css: WCAG AA in both themes.

Every text colour the page draws on a surface is a token pair here; each must
reach 4.5:1 (WCAG 2.x, normal text). The dark theme is written twice (System
and the Dark choice): both blocks must hold the same tokens.
"""

import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parents[1] / "static" / "style.css").read_text()

SURFACES = ["bg", "panel", "sunken", "raised", "face"]
TEXT = ["ink", "muted", "accent", "ok", "danger", "warn", "info", "disabled-ink"]
PAIRS = (
    [(fg, bg) for fg in TEXT for bg in SURFACES]
    + [("ink", s) for s in ["accent-soft", "ok-soft", "danger-soft", "warn-soft", "info-soft", "disabled-bg"]]
    + [("muted", "warn-soft"), ("muted", "accent-soft"), ("disabled-ink", "disabled-bg")]
    + [("ok", "ok-soft"), ("danger", "danger-soft"), ("warn", "warn-soft"), ("info", "info-soft"),
       ("accent", "accent-soft")]
    + [("accent-ink", "accent"), ("panel", "danger"), ("term-ink", "term-bg"), ("term-ink", "term-sel")]
    # selected rows (Runs, found Map rows) and the current search match
    + [(fg, "accent-soft") for fg in ["ok", "danger", "warn", "info", "muted"]]
    + [("panel", "warn")]
)


def block(*starts):
    """The declarations of the rule found by walking to each start in turn."""
    i = 0
    for start in starts:
        i = CSS.index(start, i)
    i = CSS.index("{", i)
    return CSS[i:CSS.index("}", i)]


def tokens(text):
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\b", text))


LIGHT = tokens(block(":root {"))
DARK_SYSTEM = tokens(block("@media (prefers-color-scheme: dark)", ":root:not"))
DARK_CHOICE = tokens(block(':root[data-theme="dark"]'))


def luminance(hex_):
    def ch(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(hex_[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_dark_blocks_match():
    assert DARK_SYSTEM == DARK_CHOICE
    assert len(DARK_SYSTEM) >= 25


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_text_pairs_reach_aa(theme):
    t = LIGHT if theme == "light" else DARK_SYSTEM
    low = [f"{fg} on {bg}: {ratio(t[fg], t[bg]):.2f}"
           for fg, bg in PAIRS if ratio(t[fg], t[bg]) < 4.5]
    assert low == []


def test_led_off_is_visible_on_the_face():
    """The idle LED is a non-text indicator: 1.4:1 against the readout face
    at least, so a dim LED still reads as a part, not a hole."""
    for t in (LIGHT, DARK_SYSTEM):
        assert ratio(t["led-off"], t["face"]) >= 1.4
