import json

from artoo import data


def test_pack_writes_canonical_json_and_offline_global(artifact):
    source = artifact.dir / "work" / "rows.json"
    source.write_text('[{"name":"A"}]')
    artifact.data_packs = [
        {
            "source": "work/rows.json",
            "path": "data/rows.json",
            "global": "ROWS",
        }
    ]
    result = data.pack(artifact)
    assert result.ok
    assert json.loads((artifact.site_dir / "data" / "rows.json").read_text()) == [{"name": "A"}]
    assert "window.ROWS" in (artifact.site_dir / "data" / "rows.js").read_text()


def test_pack_reports_missing_and_invalid_sources(artifact):
    artifact.data_packs = [
        {"source": "work/nope.json", "path": "data/nope.json", "global": "NOPE"}
    ]
    assert not data.pack(artifact).ok
    bad = artifact.dir / "work" / "bad.json"
    bad.write_text("{bad")
    artifact.data_packs[0]["source"] = "work/bad.json"
    assert "valid JSON" in data.pack(artifact).problems[0]
