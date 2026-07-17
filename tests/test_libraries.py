import re

import pytest

from artoo import libraries
from artoo import manifest as manifest_mod


def test_kit_available():
    libs = libraries.available()
    assert "artoo-kit" in libs
    assert (libs["artoo-kit"].root / "tokens.css").exists()


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
