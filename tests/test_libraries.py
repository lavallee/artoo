import re

import pytest

from artoo import libraries
from artoo import manifest as manifest_mod


def test_kit_available():
    libs = libraries.available()
    assert "artoo-kit" in libs
    assert (libs["artoo-kit"].root / "tokens.css").exists()


def test_kit_is_self_contained_and_exposes_accessible_type_roles():
    kit = libraries.available()["artoo-kit"]
    tokens = (kit.root / "tokens.css").read_text()
    base = (kit.root / "base.css").read_text()
    article = (kit.root / "article.css").read_text()
    components = (kit.root / "components.css").read_text()
    all_css = "\n".join((tokens, base, article, components)).lower()

    assert "color-scheme: light" in tokens
    assert '[data-theme="dark"]' in tokens
    for role in ("--font-prose", "--font-display", "--font-ui", "--font-numeric"):
        assert role in tokens
    assert "font-family: var(--font-prose)" in base
    assert "font-family: var(--font-display)" in base
    assert "font-family: var(--font-numeric)" in base
    assert "font-family: var(--font-ui)" in components
    assert "@font-face" not in all_css
    assert "url(" not in all_css


def test_controls_available_and_self_contained():
    controls = libraries.available()["artoo-controls"]
    css = (controls.root / "controls.css").read_text()
    js = (controls.root / "controls.js").read_text()
    assert "ArtooControls" in js
    assert "https://" not in css and "http://" not in css
    assert "https://" not in js and "http://" not in js


def test_kit_mobile_nav_reports_its_expanded_state():
    js = (libraries.available()["artoo-kit"].root / "kit.js").read_text()
    assert 'setAttribute("aria-expanded"' in js


def test_add_vendors_and_records(artifact):
    # scaffold already vendored the kit; verify the record and files
    m = manifest_mod.load(artifact.dir)
    assert m.libraries and m.libraries[0]["name"] == "artoo-kit"
    vendored = libraries.vendored_dir(m, "artoo-kit")
    assert (vendored / "tokens.css").exists()
    assert m.libraries[0]["sha256"] == libraries.tree_hash(vendored)


def test_status_detects_drift(artifact):
    m = manifest_mod.load(artifact.dir)
    assert libraries.status(m)[0]["state"] == "intact"
    (libraries.vendored_dir(m, "artoo-kit") / "tokens.css").write_text("/* hacked */")
    assert libraries.status(m)[0]["state"] == "modified"


def test_update_restores(artifact):
    m = manifest_mod.load(artifact.dir)
    (libraries.vendored_dir(m, "artoo-kit") / "tokens.css").write_text("/* hacked */")
    libraries.update(m, "artoo-kit")
    m = manifest_mod.load(artifact.dir)
    assert libraries.status(m)[0]["state"] == "intact"


def test_update_unknown_lib(artifact):
    m = manifest_mod.load(artifact.dir)
    with pytest.raises(KeyError):
        libraries.update(m, "never-added")


def test_status_missing_dir(artifact):
    m = manifest_mod.load(artifact.dir)
    import shutil

    shutil.rmtree(libraries.vendored_dir(m, "artoo-kit"))
    assert libraries.status(m)[0]["state"] == "missing"


def test_tree_hash_deterministic(artifact):
    m = manifest_mod.load(artifact.dir)
    d = libraries.vendored_dir(m, "artoo-kit")
    assert libraries.tree_hash(d) == libraries.tree_hash(d)


def test_callout_status_uses_type_not_side_border():
    css = (libraries.available()["artoo-kit"].root / "components.css").read_text()
    callout_rules = [
        (selectors, declarations)
        for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        if ".callout" in selectors
    ]

    assert callout_rules
    side_border = re.compile(
        r"\bborder-(?:left|right|inline-(?:start|end))(?:-[\w-]+)?\s*:"
    )
    assert not [
        selectors.strip()
        for selectors, declarations in callout_rules
        if side_border.search(declarations)
    ]

    for modifier, token in (
        ("warn", "warn"),
        ("danger", "danger"),
        ("success", "success"),
    ):
        selector = f".callout--{modifier} .callout-title"
        assert any(
            selector in selectors and f"color: var(--{token})" in declarations
            for selectors, declarations in callout_rules
        )


def test_deck_available():
    libs = libraries.available()
    assert "artoo-deck" in libs
    root = libs["artoo-deck"].root
    for name in ("deck.css", "deck.js", "favicon.svg"):
        assert (root / name).exists()


def test_deck_is_self_contained():
    """No external requests: a deck must render from file:// like any artifact."""
    deck = libraries.available()["artoo-deck"]
    css = (deck.root / "deck.css").read_text()
    js = (deck.root / "deck.js").read_text()
    assert "@font-face" not in css
    assert "url(" not in css
    assert "http://" not in css and "https://" not in css
    for forbidden in ("fetch(", "XMLHttpRequest", "import(", "src ="):
        assert forbidden not in js


def test_deck_classes_are_all_namespaced():
    """Chrome and content share one stylesheet, so chrome must not be able to
    capture a content element that happens to use the same word.

    This is a regression guard with a real incident behind it: an unprefixed
    ``.bar`` fixed-header rule set ``height: 46px`` on an SVG ``<rect
    class="bar">`` in a chart, collapsing every bar in the figure.
    """
    css = (libraries.available()["artoo-deck"].root / "deck.css").read_text()
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)  # comments name unprefixed classes
    classes = set(re.findall(r"\.([A-Za-z][\w-]*)", css))
    unprefixed = {c for c in classes if not c.startswith("deck-")}
    # Modifier classes are only ever written compounded onto a deck- class.
    allowed = {"two", "three", "four", "cool", "k", "v"}
    assert unprefixed <= allowed, f"unprefixed deck classes: {sorted(unprefixed - allowed)}"


def test_deck_prints_landscape_one_slide_per_page():
    css = (libraries.available()["artoo-deck"].root / "deck.css").read_text()
    assert "size: A4 landscape" in css
    assert "break-after: page" in css
