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
    assert "Navigation cards use `.nav-card` only" in prompt


def test_analysis_prompt_uses_ranked_graph_context_as_navigation_not_authority():
    prompt = prompts.analysis_prompt(
        "reader-repo",
        {"name": "core", "files": ["src/core.py"], "loc": 20},
        "A repository.",
        "- src/core.py:7 · function · def run()",
    )
    assert "deterministic code graph ranks" in prompt
    assert "navigation help, not proof of importance" in prompt
    assert "src/core.py:7" in prompt


def _offline(monkeypatch):
    """Simulate an offline machine: nothing in a run may reach the network."""

    def no_network(*a, **k):
        raise AssertionError("explainer must not fetch anything at generate time")

    monkeypatch.setattr("artoo.libraries.vendor_url", no_network)


def test_degraded_run(fake_repo, monkeypatch):
    # offline and without workers: must degrade gracefully, not fail the run
    _offline(monkeypatch)

    runner = CliRunner()
    result = runner.invoke(generate, ["--repo", str(fake_repo)])
    assert result.exit_code == 0, result.output

    out = fake_repo / "site" / "explainer"
    site = out / "site"
    assert (site / "index.html").is_file()
    assert (site / "architecture.html").is_file()
    assert (site / "reference.html").is_file()
    assert (site / "code-map.html").is_file()
    assert (site / "lib" / "artoo-kit" / "tokens.css").is_file()
    assert (site / "lib" / "artoo-map" / "cytoscape.min.js").is_file()
    assert (site / "data" / "codegraph.json").is_file()
    assert (site / "data" / "codegraph.js").is_file()
    assert (out / "work" / "codegraph.generated.json").is_file()

    index = (site / "index.html").read_text()
    assert "Deterministic build" in index  # honest about degraded mode
    assert "colophon" in index
    assert "fake-repo" in index
    assert 'data-theme="light"' in index
    assert "data-theme-toggle" not in index
    assert "stat-row" not in index
    assert "card-grid" not in index

    map_page = (site / "code-map.html").read_text()
    assert 'class="map article-breakout"' in map_page
    assert 'src="lib/artoo-map/cytoscape.min.js"' in map_page
    assert 'src="data/codegraph.js"' in map_page
    assert "ArtooMap.create" in map_page

    graph = json.loads((site / "data" / "codegraph.json").read_text())
    assert graph["contract"] == "artoo-codegraph/1"
    assert not any(
        path.startswith("/")
        for node in graph["nodes"]
        if (path := node.get("path", ""))
    )

    plan = json.loads((out / "work" / "plan.json").read_text())
    assert plan["pages"][0]["slug"] == "index"
    assert any(page["slug"] == "code-map" for page in plan["pages"])

    # inventory excluded the artifact's own directory
    inv = json.loads((out / "work" / "inventory.json").read_text())
    assert not any(f["path"].startswith("site/explainer") for f in inv["files"])


def test_rerun_reuses_artifact(fake_repo, monkeypatch):
    _offline(monkeypatch)
    runner = CliRunner()
    first = runner.invoke(generate, ["--repo", str(fake_repo)])
    assert first.exit_code == 0
    second = runner.invoke(generate, ["--repo", str(fake_repo)])
    assert second.exit_code == 0
    assert "updating artifact" in second.output


def test_diagrams_render_offline_from_the_builtin_library(fake_repo, monkeypatch):
    """Diagram pages vendor artoo-diagrams; no CDN, no optional package."""
    _offline(monkeypatch)
    result = CliRunner().invoke(generate, ["--repo", str(fake_repo)])
    assert result.exit_code == 0, result.output

    site = fake_repo / "site" / "explainer" / "site"
    assert (site / "lib" / "artoo-diagrams" / "pele.global.js").is_file()
    arch = (site / "architecture.html").read_text()
    assert 'class="mermaid"' in arch
    assert '<link rel="stylesheet" href="lib/artoo-diagrams/diagrams.css">' in arch
    assert '<script src="lib/artoo-diagrams/pele.global.js"></script>' in arch
    assert '<script src="lib/artoo-diagrams/diagrams.js"></script>' in arch
    assert "mermaid.min.js" not in arch
    reference = (site / "reference.html").read_text()
    assert 'class="mermaid"' not in reference
    assert "pele.global.js" not in reference  # 700 KB only where a diagram is

    import artoo.manifest as manifest_mod

    m = manifest_mod.load(fake_repo / "site" / "explainer")
    assert any(lib["name"] == "artoo-diagrams" for lib in m.libraries)


def test_recorded_mermaid_library_is_kept(fake_repo, tmp_path, monkeypatch):
    """An artifact that opted into artoo-mermaid keeps mermaid.js on rerun."""
    from artoo import libraries as libraries_mod
    from artoo.libraries import Library

    _offline(monkeypatch)
    assets = tmp_path / "mermaid-assets"
    assets.mkdir()
    (assets / "mermaid.min.js").write_text("/* fake mermaid */")
    fake_lib = Library(name="mermaid", version="99.0-test", root=assets)
    real_get = libraries_mod.get
    monkeypatch.setattr(
        "artoo.libraries.get",
        lambda name: fake_lib if name == "mermaid" else real_get(name),
    )

    assert CliRunner().invoke(generate, ["--repo", str(fake_repo)]).exit_code == 0
    import artoo.manifest as manifest_mod

    m = manifest_mod.load(fake_repo / "site" / "explainer")
    m.libraries = [lib for lib in m.libraries if lib["name"] != "artoo-diagrams"]
    m.save()
    libraries_mod.add(manifest_mod.load(m.dir), "mermaid")

    result = CliRunner().invoke(generate, ["--repo", str(fake_repo)])
    assert result.exit_code == 0, result.output
    arch = (m.site_dir / "architecture.html").read_text()
    assert '<script src="lib/mermaid/mermaid.min.js"></script>' in arch
    assert "pele.global.js" not in arch