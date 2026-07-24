"""Read-side flip integration (subprocess, graceful degradation)."""

from artoo import flip_read

from conftest import SAMPLE_PROJECTION


def test_absent_flip_degrades(monkeypatch, tmp_path):
    # No ARTOO_FLIP_BIN and no `flip` on a scrubbed PATH.
    monkeypatch.delenv("ARTOO_FLIP_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert flip_read.flip_bin() is None
    assert not flip_read.available()
    data, reason = flip_read.export_json(tmp_path)
    assert data is None and "not installed" in reason
    findings, reason = flip_read.doctor_json(tmp_path)
    assert findings is None and "not installed" in reason


def test_pin_must_resolve(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTOO_FLIP_BIN", str(tmp_path / "nope"))
    assert flip_read.flip_bin() is None


def test_export_json_via_stub(flip_stub, tmp_path):
    flip_stub.set_export(SAMPLE_PROJECTION)
    data, reason = flip_read.export_json(tmp_path)
    assert reason == ""
    assert data["contract"] == "flip-render/1"
    assert [c["id"] for c in data["claims"]] == ["C1", "C2"]


def test_export_json_refusal(flip_stub, tmp_path):
    flip_stub.refuse_export("notebook visibility is 'internal'")
    data, reason = flip_read.export_json(tmp_path)
    assert data is None
    assert "internal" in reason


def test_doctor_json_clean_and_errors(flip_stub, tmp_path):
    flip_stub.set_doctor([])
    findings, reason = flip_read.doctor_json(tmp_path)
    assert findings == [] and reason == ""

    flip_stub.set_doctor([{"level": "ERROR", "code": "dangling-citation", "message": "C3 cites A9"}])
    findings, reason = flip_read.doctor_json(tmp_path)
    assert reason == ""
    assert findings[0]["level"] == "ERROR"


def test_read_vintage_from_frontmatter(notebook_artifact):
    vintage = flip_read.read_vintage(notebook_artifact.dir / "notebook")
    assert vintage == {"uid": "nb-abc123", "updated": "2026-07-24"}


def test_read_vintage_missing(tmp_path):
    assert flip_read.read_vintage(tmp_path) is None
