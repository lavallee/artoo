import json

import pytest
from click.testing import CliRunner

from artoo import content, edit, manifest, scaffold
from artoo.cli import main


def _artifact(tmp_path):
    m = scaffold.init_artifact(tmp_path / "book", title="Book", kind="reference-guide")
    for path in (m.dir / "content").glob("*.md"):
        path.unlink()
    (m.dir / "content" / "index.md").write_text("# Front\n\nHello.\n")
    m.content_order = ["index.md"]
    m.content_sourcemap = True
    m.edit_comments = "edit/comments.json"
    m.edit_status = "edit/status.json"
    m.save()
    m = manifest.load(m.dir)
    content.render(m)
    return m


def test_generated_config_registers_mapped_markdown_and_edit_files(tmp_path):
    m = _artifact(tmp_path)
    path = edit.config_path(m, 9000)
    config = json.loads(path.read_text())
    page = config["pages"][0]
    assert config["root"] == "../.." and path == m.dir / "work/editor/copycat.json"
    assert page["serve"] == {"dir": "site", "path": f"/{m.slug}/"}
    assert page["sourcemap"] == "work/artoo-sourcemap.json"
    files = [s["file"] for s in page["sources"]]
    assert files == ["artifact.toml", "content/index.md"]
    assert page["comments"] == "edit/comments.json" and page["status"] == {"file": "edit/status.json"}
    assert (m.dir / "edit").is_dir()


def test_declared_config_is_used_as_is(tmp_path):
    m = _artifact(tmp_path)
    m.edit_config = "editor.json"
    with pytest.raises(edit.EditError, match="does not exist"):
        edit.config_path(m, 9000)
    (m.dir / "editor.json").write_text("{}")
    assert edit.config_path(m, 9000) == m.dir / "editor.json"


def test_road_signs(tmp_path, monkeypatch):
    monkeypatch.delenv("COPYCAT_HOME", raising=False)
    with pytest.raises(edit.EditError, match="COPYCAT_HOME"):
        edit.copycat_home()
    with pytest.raises(edit.EditError, match="not a Copycat checkout"):
        edit.copycat_home(tmp_path)
    with pytest.raises(edit.EditError, match="exact https"):
        edit.check_origin("http://x.example")
    assert edit.check_origin("https://x.example") == "https://x.example"


def test_command_carries_port_origin_and_agent(tmp_path, monkeypatch):
    m = _artifact(tmp_path)
    copycat = tmp_path / "copycat"
    (copycat / "src").mkdir(parents=True)
    (copycat / "src" / "server.js").write_text("")
    monkeypatch.setattr(edit.shutil, "which", lambda name: "/usr/bin/node")
    argv, env = edit.command(m, copycat=edit.copycat_home(copycat), port=9001,
                             share_origin="https://x.example", agent="codex", agent_bin="/bin/codex")
    assert argv == ["/usr/bin/node", str(copycat.resolve() / "src/server.js")]
    assert (env["PORT"], env["HOST"], env["COPYCAT_HOST_ORIGINS"]) == ("9001", "127.0.0.1", "https://x.example")
    assert (env["COPYCAT_AGENT_PRESET"], env["COPYCAT_AGENT_BIN"]) == ("codex", "/bin/codex")
    with pytest.raises(edit.EditError, match="agent-bin"):
        edit.command(m, copycat=copycat, port=1, agent="claude")


def test_cli_edit_needs_a_source_map_and_evidence_reads_it(tmp_path):
    m = _artifact(tmp_path)
    runner = CliRunner()
    out = runner.invoke(main, ["evidence", str(m.dir)])
    assert out.exit_code == 0 and "no evidence in the map" in out.output
    out = runner.invoke(main, ["edit", str(m.dir), "--print-config"])
    assert out.exit_code == 0 and '"sourcemap"' in out.output
    m.content_sourcemap = False
    m.save()
    out = runner.invoke(main, ["edit", str(m.dir)])
    assert out.exit_code != 0 and "sourcemap = true" in out.output



def test_live_is_opt_in_and_names_the_kit_containers(tmp_path):
    m = _artifact(tmp_path)
    plain = json.loads(edit.config_path(m, 9000).read_text())["pages"][0]["sources"]
    assert all("live" not in s for s in plain)
    m.edit_live = True
    live = json.loads(edit.config_path(m, 9000).read_text())["pages"][0]["sources"]
    markdown = [s for s in live if s.get("markdown")]
    assert markdown and all(s["live"] is True and s["containers"]["wide"] == "div.article-breakout" for s in markdown)
    assert "live" not in live[0]


def _deck(tmp_path, **init):
    return scaffold.init_artifact(tmp_path / "talk", title="Talk", **({"form": "deck"} | init))


def test_a_deck_is_edited_as_html_with_no_source_map(tmp_path):
    m = _deck(tmp_path)
    assert edit.is_deck(m) and not m.content_sourcemap
    path = edit.config_path(m, 9000)
    config = json.loads(path.read_text())
    page = config["pages"][0]
    assert path == m.dir / "work/editor/copycat.json" and config["root"] == "../.."
    assert page["deck"] is True and page["name"] == "Talk" and page["selector"] == "main.deck-stage"
    assert page["url"] == f"http://127.0.0.1:9000/{m.slug}/index.html"
    assert page["serve"] == {"dir": "site", "path": f"/{m.slug}/"} and "sourcemap" not in page
    assert page["sources"] == [{
        "file": "site/index.html", "html": True, "live": True, "scope": "main.deck-stage", "label": "Slides",
        "attributes": ["data-short", "data-act", "alt", "title"], "svgText": ".deck-figure", "status": False,
    }]
    # Nothing is rendered from a deck, so the command after a save is a check, not a rebuild.
    assert page["build"] == {"command": ["artoo", "build", "--no-browser", "."], "timeout": 120, "check": True}
    assert "comments" not in page and "status" not in page


def test_a_deck_takes_comments_and_status_from_edit_and_briefs_the_agent(tmp_path):
    m = _deck(tmp_path, kind="presentation", form="")
    assert m.effective_form == "deck"
    m.edit_comments = "edit/comments.json"
    m.edit_status = "edit/status.json"
    page = json.loads(edit.config_path(m, 9000).read_text())["pages"][0]
    assert page["comments"] == "edit/comments.json" and page["status"] == {"file": "edit/status.json"}
    assert page["sources"][0]["status"] is True and (m.dir / "edit").is_dir()
    brief = page["chat"]["format"]
    # The markup contract and the prefix rule, in the library's own vocabulary.
    for needle in ('<main class="deck-stage" data-deck>', "data-act", "data-short", '<aside class="deck-notes">',
                   "Never invent a class that starts with deck-", "deck-callout", "deck-stat-row", "deck-grid"):
        assert needle in brief
    for chrome in ("deck-ov-item", "deck-bar,", "deck-progress"):
        assert chrome not in brief.split("use only these content classes")[1].split(". Never")[0]


def test_deck_road_signs_and_the_cli(tmp_path):
    m = _deck(tmp_path)
    runner = CliRunner()
    out = runner.invoke(main, ["edit", str(m.dir), "--print-config"])
    assert out.exit_code == 0 and '"deck": true' in out.output and '"html": true' in out.output
    (m.dir / "site" / "index.html").unlink()
    out = runner.invoke(main, ["edit", str(m.dir), "--print-config"])
    assert out.exit_code != 0 and "no site/index.html to edit" in out.output
    # A deck rendered from Markdown is not this path: it needs its source map like any page.
    m.content_source = "content.md"
    assert not edit.is_deck(m)


def test_the_deck_script_keeps_its_contract_and_serves_an_editor(tmp_path):
    from artoo.libraries import deck

    script = (deck.library.root / "deck.js").read_text()
    assert deck.VERSION == "0.2.0" and 'version: "0.2.0"' in script
    # What an older deck relies on is still there.
    for needle in ('querySelector("[data-deck]")', '"data-short"', '"data-act"', "deck-show-notes", "hashchange"):
        assert needle in script
    # What an editor relies on: text keeps its keys and swipes, and the slides can be read again.
    for needle in ("window.artooDeck", "refresh: refresh", "event.defaultPrevented", "composedPath", "deck:change"):
        assert needle in script
    assert "overscroll-behavior-x: none" in (deck.library.root / "deck.css").read_text()
