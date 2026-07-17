import json

from click.testing import CliRunner

from artoo.generators import available
from artoo.generators.explainer import _default_plan, _extract_json, _strip_fences, generate
from artoo.generators.explainer import prompts


def test_registered():
    assert "explainer" in available()


def test_extract_json():
    assert _extract_json('noise {"a": 1} trailing') == {"a": 1}
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json("no json here") is None


def test_strip_fences():
    assert _strip_fences("```html\n<p>x</p>\n```") == "<p>x</p>"
    assert _strip_fences("<p>x</p>") == "<p>x</p>"


def _prompt_inventory():
    return {
        "name": "reader-repo",
        "loc_by_extension": {".py": 10},
        "python": {"source_loc": 8, "test_loc": 2, "packages": []},
        "readme": {"first_paragraph": "A repo for readers."},
    }


def test_planning_prompt_is_argument_first():
    prompt = " ".join(
        prompts.plan_prompt(_prompt_inventory(), {"core": "A grounded brief."}).split()
    )
    for contract_term in (
        "reader decision",
        "headline claim",
        "evidence limits",
        "counter-reading",
        "licit comparisons",
        "selected_forms",
        "units, vintages, denominators",
    ):
        assert contract_term in prompt
    assert "form directly helps the reader" in prompt
    assert "dashboard shell" in prompt


def test_page_prompt_selects_evidence_forms_instead_of_component_composition():
    inv = _prompt_inventory()
    plan = _default_plan(inv)
    page = plan["pages"][0]
    prompt = " ".join(
        prompts.page_prompt(
            inv, plan, page, {"core": "Ground truth at src/core.py:1."}
        ).split()
    )

    for contract_term in (
        "Reader decision:",
        "Headline claim:",
        "Evidence limits:",
        "Counter-reading:",
        "Licit comparisons:",
        "Selected forms and reasons:",
        "supports a licit reader comparison",
        "margin notes for definitions and file-level provenance",
    ):
        assert contract_term in prompt
    assert "a stat-row or pullnumber" not in prompt
    assert "cards for links to related pages" not in prompt
    assert "Cards are available only for true navigation" in prompt


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
    assert 'data-theme="light"' in index
    assert "data-theme-toggle" not in index
    assert "stat-row" not in index
    assert "card-grid" not in index

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
