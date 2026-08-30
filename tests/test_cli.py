import json

import click
import pytest
from click.testing import CliRunner

from artoo import manifest as manifest_mod
from artoo.cli import main

from conftest import SAMPLE_PROJECTION


def invoke(*args):
    return CliRunner().invoke(main, list(args))


def _attach_notebook(art_dir):
    """Attach a fake flip notebook whose vintage matches SAMPLE_PROJECTION."""
    nb = art_dir / "notebook"
    nb.mkdir(exist_ok=True)
    (nb / "index.md").write_text(
        "---\nuid: nb-abc123\nupdated: '2026-07-24'\nvisibility: public\n---\n# nb\n",
        encoding="utf-8",
    )
    man = manifest_mod.load(art_dir)
    man.notebook = "notebook"
    man.save()


def test_version():
    from artoo import __version__

    result = invoke("--version")
    assert result.exit_code == 0
    assert __version__ in result.output


def test_init_and_status(tmp_path):
    result = invoke("init", str(tmp_path / "art"), "--kind", "note", "--title", "A note")
    assert result.exit_code == 0, result.output
    result = invoke("status", str(tmp_path / "art"))
    assert result.exit_code == 0
    assert "manifest, firewall, markup, and static verification clean" in result.output


def test_init_creates_article_source_and_private_artifact_brief(tmp_path):
    artifact = tmp_path / "art"
    result = invoke(
        "init",
        str(artifact),
        "--title",
        "A public finding",
        "--description",
        "Evidence for a reader decision.",
    )
    assert result.exit_code == 0, result.output
    assert "work/artifact-brief.md (private)" in result.output

    page = (artifact / "site" / "index.html").read_text()
    assert '<html lang="en" data-theme="light">' in page
    for editorial_surface in (
        "article-masthead",
        "article-header",
        "article-title",
        "article-dek",
        "article-byline",
    ):
        assert editorial_surface in page
    for dashboard_default in ("data-theme-toggle", "stat-row", "card-grid"):
        assert dashboard_default not in page

    assert (artifact / "content.md").is_file()
    brief = (artifact / "work" / "artifact-brief.md").read_text()
    assert not (artifact / "site" / "work" / "artifact-brief.md").exists()
    for field in (
        "## Reader decision",
        "## Headline claim",
        "## Supported claims",
        "## Unsupported claims and counter-reading",
        "## Data vintages and denominators",
        "## Licit comparisons",
        "## Selected forms",
        "## Presentation intent",
        "## Anti-reference",
        "## Proof required",
    ):
        assert field in brief


def test_init_refuses_existing(tmp_path):
    invoke("init", str(tmp_path / "art"))
    result = invoke("init", str(tmp_path / "art"))
    assert result.exit_code != 0


def test_list(tmp_path):
    invoke("init", str(tmp_path / "one"), "--kind", "note")
    invoke("init", str(tmp_path / "two"), "--kind", "report")
    result = invoke("list", str(tmp_path))
    assert "one" in result.output and "two" in result.output


def test_build(tmp_path):
    invoke("init", str(tmp_path / "art"))
    result = invoke("build", str(tmp_path / "art"))
    assert result.exit_code == 0
    assert "site ready" in result.output


def test_deploy_requires_target(tmp_path):
    invoke("init", str(tmp_path / "art"))
    result = invoke("deploy", str(tmp_path / "art"))
    assert result.exit_code != 0
    assert "no [deploy] target" in result.output


def test_doctor(tmp_path):
    invoke("init", str(tmp_path / "art"))
    result = invoke("doctor", str(tmp_path))
    assert result.exit_code == 0
    assert "1/1 artifacts clean" in result.output


def test_generate_lists_generators():
    result = invoke("generate", "--help")
    assert "explainer" in result.output


def test_lib_flow(tmp_path):
    invoke("init", str(tmp_path / "art"))
    result = invoke("lib", "status", "--artifact", str(tmp_path / "art"))
    assert "artoo-kit" in result.output and "intact" in result.output
    result = invoke("lib", "update", "artoo-kit", "--artifact", str(tmp_path / "art"))
    assert result.exit_code == 0


# -- flip roundtrip surfaces --------------------------------------------------


def test_init_ships_favicon(tmp_path):
    invoke("init", str(tmp_path / "art"))
    page = (tmp_path / "art" / "site" / "index.html").read_text()
    assert 'rel="icon"' in page and "favicon.svg" in page
    assert (tmp_path / "art" / "site" / "lib" / "artoo-kit" / "favicon.svg").is_file()


def test_provenance_command(tmp_path, flip_stub):
    invoke("init", str(tmp_path / "art"))
    _attach_notebook(tmp_path / "art")
    flip_stub.set_export(SAMPLE_PROJECTION)
    result = invoke("provenance", str(tmp_path / "art"))
    assert result.exit_code == 0, result.output
    assert "wrote" in result.output and "sources" in result.output
    assert (tmp_path / "art" / "site" / "data" / "provenance.json").is_file()
    assert (tmp_path / "art" / "site" / "data" / "provenance.js").is_file()


def test_provenance_command_skips_without_notebook(tmp_path, flip_stub):
    invoke("init", str(tmp_path / "art"))
    result = invoke("provenance", str(tmp_path / "art"))
    assert result.exit_code == 0
    assert "skipped" in result.output


def test_status_reports_freshness(tmp_path, flip_stub):
    invoke("init", str(tmp_path / "art"))
    _attach_notebook(tmp_path / "art")
    flip_stub.set_export(SAMPLE_PROJECTION)
    invoke("provenance", str(tmp_path / "art"))
    result = invoke("status", str(tmp_path / "art"))
    assert "render fresh" in result.output


def test_build_flags_bad_data_json(tmp_path):
    invoke("init", str(tmp_path / "art"))
    data = tmp_path / "art" / "site" / "data"
    data.mkdir(parents=True)
    (data / "bad.json").write_text("{oops")
    result = invoke("build", str(tmp_path / "art"))
    assert result.exit_code != 0
    assert "invalid JSON" in result.output


def test_deploy_blocks_on_doctor_errors(tmp_path, flip_stub):
    invoke("init", str(tmp_path / "art"))
    _attach_notebook(tmp_path / "art")
    man = manifest_mod.load(tmp_path / "art")
    man.deploy_target = "command"
    man.deploy_config = {"command": "true"}
    man.save()
    flip_stub.set_doctor([{"level": "ERROR", "code": "dangling-citation", "message": "C3 cites A9"}])
    result = invoke("deploy", str(tmp_path / "art"), "--dry-run")
    assert result.exit_code != 0
    assert "flip doctor found" in result.output


def test_deploy_gate_helper_paths(notebook_artifact, flip_stub):
    from artoo.cli import _deploy_doctor_gate

    flip_stub.set_doctor([{"level": "WARN", "code": "x", "message": "w"}])
    _deploy_doctor_gate(notebook_artifact, False)  # WARN alone does not block

    flip_stub.set_doctor([{"level": "ERROR", "code": "x", "message": "boom"}])
    with pytest.raises(click.ClickException):
        _deploy_doctor_gate(notebook_artifact, False)
    _deploy_doctor_gate(notebook_artifact, True)  # override does not raise


# -- machine-readable output ------------------------------------------------


def test_status_json_separates_markup_findings_from_manifest_problems(artifact):
    """A caller fixing markup wants the class and the suggestion as fields —
    not a sentence to re-parse out of a list of unrelated problems."""
    index = artifact.site_dir / "index.html"
    index.write_text(index.read_text().replace("</main>", '<p class="article-ful"></p></main>'))

    result = CliRunner().invoke(main, ["status", str(artifact.dir), "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)

    assert report["problems"] == []
    assert report["ok"] is False
    assert report["markup"][0]["class"] == "article-ful"
    assert report["markup"][0]["suggestion"] == "article-full"
    assert report["markup"][0]["library"] == "artoo-kit"


def test_status_json_on_a_clean_artifact(artifact):
    result = CliRunner().invoke(main, ["status", str(artifact.dir), "--json"])
    report = json.loads(result.output)
    assert report["ok"] is True
    assert report["slug"] == artifact.slug
    assert report["libraries"][0]["state"] == "intact"


def test_build_json_exits_nonzero_while_still_emitting_the_report(artifact):
    """A failing build has to stay parseable; a caller that cannot read the
    problems has to fall back to scraping stderr."""
    index = artifact.site_dir / "index.html"
    artifact.content_source = ""
    artifact.save()
    index.write_text(index.read_text().replace("</main>", '<p class="article-wide"></p></main>'))

    result = CliRunner().invoke(main, ["build", str(artifact.dir), "--json"])
    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report["ok"] is False
    assert any("article-wide" in p for p in report["problems"])


def test_build_json_reports_a_clean_build(artifact):
    result = CliRunner().invoke(main, ["build", str(artifact.dir), "--json"])
    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["ok"] is True
    assert report["stamped"]


def test_doctor_json_covers_every_artifact_in_the_tree(artifact):
    result = CliRunner().invoke(main, ["doctor", str(artifact.dir.parent), "--json"])
    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["total"] == 1
    assert report["clean"] == 1
    assert report["artifacts"][0]["slug"] == artifact.slug


def test_doctor_counts_a_markup_finding_as_unclean(artifact):
    index = artifact.site_dir / "index.html"
    index.write_text(index.read_text().replace("</main>", '<p class="article-wide"></p></main>'))
    result = CliRunner().invoke(main, ["doctor", str(artifact.dir.parent), "--json"])
    report = json.loads(result.output)
    assert report["clean"] == 0
    assert report["artifacts"][0]["markup"]
