import json

from click.testing import CliRunner

from artoo.generators import available
from artoo.generators.explainer import _extract_json, _strip_fences, generate


def test_registered():
    assert "explainer" in available()


def test_extract_json():
    assert _extract_json('noise {"a": 1} trailing') == {"a": 1}
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json("no json here") is None


def test_strip_fences():
    assert _strip_fences("```html\n<p>x</p>\n```") == "<p>x</p>"
    assert _strip_fences("<p>x</p>") == "<p>x</p>"


def _no_mermaid(monkeypatch):
    """Simulate: artoo-mermaid not installed AND offline."""
    from artoo import libraries as libraries_mod

    real_get = libraries_mod.get

    def no_mermaid_lib(name):
        if name == "mermaid":
            raise KeyError(name)
        return real_get(name)

    def no_network(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr("artoo.libraries.get", no_mermaid_lib)
    monkeypatch.setattr("artoo.libraries.vendor_url", no_network)


def test_degraded_run(fake_repo, monkeypatch):
    # offline, no mermaid library: must degrade gracefully, not fail the run
    _no_mermaid(monkeypatch)

    runner = CliRunner()
    result = runner.invoke(generate, ["--repo", str(fake_repo)])
    assert result.exit_code == 0, result.output

    out = fake_repo / "site" / "explainer"
    site = out / "site"
    assert (site / "index.html").is_file()
    assert (site / "architecture.html").is_file()
    assert (site / "reference.html").is_file()
    assert (site / "lib" / "artoo-kit" / "tokens.css").is_file()

    index = (site / "index.html").read_text()
    assert "Deterministic build" in index  # honest about degraded mode
    assert "colophon" in index
    assert "fake-repo" in index

    plan = json.loads((out / "work" / "plan.json").read_text())
    assert plan["pages"][0]["slug"] == "index"

    # inventory excluded the artifact's own directory
    inv = json.loads((out / "work" / "inventory.json").read_text())
    assert not any(f["path"].startswith("site/explainer") for f in inv["files"])


def test_rerun_reuses_artifact(fake_repo, monkeypatch):
    _no_mermaid(monkeypatch)
    runner = CliRunner()
    first = runner.invoke(generate, ["--repo", str(fake_repo)])
    assert first.exit_code == 0
    second = runner.invoke(generate, ["--repo", str(fake_repo)])
    assert second.exit_code == 0
    assert "updating artifact" in second.output


def test_mermaid_from_site_library(fake_repo, tmp_path, monkeypatch):
    """With the artoo-mermaid library installed, the explainer vendors it
    instead of hitting the CDN."""
    from artoo.libraries import Library

    assets = tmp_path / "mermaid-assets"
    assets.mkdir()
    (assets / "mermaid.min.js").write_text("/* fake mermaid */")
    fake_lib = Library(name="mermaid", version="99.0-test", root=assets)

    from artoo import libraries as libraries_mod

    real_get = libraries_mod.get
    monkeypatch.setattr(
        "artoo.libraries.get",
        lambda name: fake_lib if name == "mermaid" else real_get(name),
    )
    monkeypatch.setattr(
        "artoo.libraries.vendor_url",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not hit CDN")),
    )

    result = CliRunner().invoke(generate, ["--repo", str(fake_repo)])
    assert result.exit_code == 0, result.output

    site = fake_repo / "site" / "explainer" / "site"
    assert (site / "lib" / "mermaid" / "mermaid.min.js").exists()
    arch = (site / "architecture.html").read_text()
    assert '<script src="lib/mermaid/mermaid.min.js"></script>' in arch

    import artoo.manifest as manifest_mod

    m = manifest_mod.load(fake_repo / "site" / "explainer")
    assert any(
        lib["name"] == "mermaid" and lib["version"] == "99.0-test"
        for lib in m.libraries
    )
