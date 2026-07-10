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


def test_degraded_run(fake_repo, monkeypatch):
    # offline: vendoring mermaid must degrade gracefully, not fail the run
    def no_network(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr("artoo.libraries.vendor_url", no_network)

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
    monkeypatch.setattr("artoo.libraries.vendor_url", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    runner = CliRunner()
    first = runner.invoke(generate, ["--repo", str(fake_repo)])
    assert first.exit_code == 0
    second = runner.invoke(generate, ["--repo", str(fake_repo)])
    assert second.exit_code == 0
    assert "updating artifact" in second.output
