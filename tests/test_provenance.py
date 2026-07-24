"""Provenance ingestion, staleness, and data-JSON validation."""

import json

from artoo import manifest as manifest_mod
from artoo import provenance

from conftest import SAMPLE_PROJECTION


def test_ingest_writes_projection_and_stamps_vintage(notebook_artifact, flip_stub):
    flip_stub.set_export(SAMPLE_PROJECTION)
    result = provenance.ingest(notebook_artifact)
    assert result.status == "written"

    dest = notebook_artifact.site_dir / "data" / "provenance.json"
    assert dest.is_file()
    data = json.loads(dest.read_text())
    assert data["contract"] == "flip-render/1"

    # Offline (file://) global loader written alongside.
    js = (notebook_artifact.site_dir / "data" / "provenance.js").read_text()
    assert "window.__ARTOO_PROVENANCE__" in js

    # Vintage stamped into the manifest and persisted.
    assert result.vintage == {"uid": "nb-abc123", "updated": "2026-07-24"}
    reloaded = manifest_mod.load(notebook_artifact.path)
    assert reloaded.rendered_uid == "nb-abc123"
    assert reloaded.rendered_updated == "2026-07-24"

    assert result.counts["sources"] == 2
    assert result.counts["grades"] == {"A": 1, "B": 1}
    assert result.counts["load_bearing"] == 1


def test_ingest_skips_without_notebook(artifact, flip_stub):
    result = provenance.ingest(artifact)
    assert result.status == "skipped"
    assert "no flip notebook" in result.note


def test_ingest_skips_without_flip(notebook_artifact, monkeypatch, tmp_path):
    monkeypatch.delenv("ARTOO_FLIP_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    result = provenance.ingest(notebook_artifact)
    assert result.status == "skipped"
    assert "flip is not installed" in result.note


def test_ingest_error_on_policy_refusal(notebook_artifact, flip_stub):
    flip_stub.refuse_export("notebook visibility is 'internal'")
    result = provenance.ingest(notebook_artifact)
    assert result.status == "error"
    assert "internal" in result.note


def test_include_private_opt_in_reaches_flip(notebook_artifact, flip_stub, monkeypatch):
    # The manifest opt-in must add --include-private to the flip invocation.
    seen = {}
    real = provenance.flip_read.export_json

    def spy(nb_dir, *, include_private=False):
        seen["include_private"] = include_private
        return real(nb_dir, include_private=include_private)

    monkeypatch.setattr(provenance.flip_read, "export_json", spy)
    flip_stub.set_export(SAMPLE_PROJECTION)

    notebook_artifact.research_include_private = True
    notebook_artifact.save()
    provenance.ingest(notebook_artifact)
    assert seen["include_private"] is True


def test_staleness_states(notebook_artifact, flip_stub):
    # No recorded vintage yet.
    assert provenance.staleness(notebook_artifact)["state"] == "never"

    flip_stub.set_export(SAMPLE_PROJECTION)
    provenance.ingest(notebook_artifact)
    assert provenance.staleness(notebook_artifact)["state"] == "fresh"

    # Notebook moves on: bump the live frontmatter `updated`.
    index = notebook_artifact.dir / "notebook" / "index.md"
    index.write_text(index.read_text().replace("2026-07-24", "2026-08-01"), encoding="utf-8")
    assert provenance.staleness(notebook_artifact)["state"] == "stale"


def test_staleness_none_without_notebook(artifact):
    assert provenance.staleness(artifact)["state"] == "none"


def test_staleness_unknown_when_notebook_unreadable(artifact):
    artifact.notebook = "notebook"  # declared but no index.md on disk
    assert provenance.staleness(artifact)["state"] == "unknown"


def test_data_json_problems(artifact):
    data_dir = artifact.site_dir / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "good.json").write_text('{"ok": true}')
    assert provenance.data_json_problems(artifact.site_dir) == []
    (data_dir / "bad.json").write_text("{not json")
    problems = provenance.data_json_problems(artifact.site_dir)
    assert len(problems) == 1
    assert "bad.json" in problems[0]
