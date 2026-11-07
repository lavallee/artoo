"""Named looks: every manifest look exists in the kit, in light and dark, at AA."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from artoo import content, libraries, manifest

TOKENS = Path(libraries.get("artoo-kit").root, "tokens.css").read_text()


def _block(selector: str) -> dict[str, str]:
    match = re.search(re.escape(selector) + r"\s*\{(.*?)\}", TOKENS, re.S)
    assert match, f"tokens.css has no {selector} block"
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", match.group(1)))


def _lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _ratio(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("look", [name for name in manifest.LOOKS if name != "editorial"])
@pytest.mark.parametrize("dark", [False, True])
def test_every_look_meets_aa_on_every_surface(look, dark):
    selector = f'[data-look="{look}"]' + ('[data-theme="dark"]' if dark else "")
    tokens = _block(selector)
    for fg in ("--text", "--text-2", "--muted", "--accent"):
        for bg in ("--bg", "--surface", "--surface-2"):
            ratio = _ratio(tokens[fg], tokens[bg])
            assert ratio >= 4.5, f"{selector} {fg} on {bg} is {ratio:.2f}:1"


def test_look_lands_on_html_and_default_adds_nothing(tmp_path):
    m = manifest.new("demo", "Demo")
    m.content_source = "content.md"
    m.look = "broadsheet"
    m.save(tmp_path)
    libraries.add(m, "artoo-kit")
    (tmp_path / "content.md").write_text("# Demo\n\nText.\n")
    content.render(manifest.load(tmp_path))
    assert '<html lang="en" data-theme="light" data-look="broadsheet">' in (
        tmp_path / "site" / "index.html"
    ).read_text()
    m = manifest.load(tmp_path)
    m.look = "editorial"
    m.save()
    content.render(manifest.load(tmp_path))
    assert "data-look" not in (tmp_path / "site" / "index.html").read_text()
