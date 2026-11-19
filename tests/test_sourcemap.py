import hashlib
import json
import re

from artoo import content, manifest, scaffold, sourcemap


def _collection(tmp_path, order=("index.md", "one.md")):
    artifact = scaffold.init_artifact(tmp_path / "book", title="Book", kind="reference-guide")
    pages = artifact.dir / "content"
    for path in pages.glob("*.md"):
        path.unlink()
    artifact.content_order = list(order)
    artifact.content_sourcemap = True
    artifact.save()
    return manifest.load(artifact.dir), pages


def _block(data, page, element_id):
    return next(b for b in data["pages"][page]["blocks"] if b["id"] == element_id)


def _ids(html, tag):
    return re.findall(rf'<{tag}[^>]*data-artoo-src="(a\d+)"', html)


def test_split_maps_lines_through_origin_comments():
    source = (
        "<!-- artoo:source content.md:1 -->\n---\ndescription: Dek\n---\n\n# Title\n"
        "<!-- artoo:source book/one.md:3 -->\nPara one\n\nPara two\n"
        "<!-- artoo:source - -->\n<p>generated</p>\n"
    )
    clean, origins = sourcemap.split(source, "work/pages/index.md")
    lines = clean.split("\n")
    assert lines[0] == "---"  # front matter still opens the page
    assert "artoo:source" not in clean
    assert origins[lines.index("# Title")] == sourcemap.Origin("content.md", 5)
    assert origins[lines.index("Para two")] == sourcemap.Origin("book/one.md", 5)
    assert origins[lines.index("<p>generated</p>")].file == "-"
    assert sourcemap.split("Plain\n", "p.md")[1][0] == sourcemap.Origin("p.md", 1)


def test_numbers_ignore_years_and_round_decimal_shares():
    found = sourcemap.numbers("In 2026 Catbird held 66.1% of 18,797 pickups across 35 of 118 stories")
    assert {"66.1%", "66%", "18,797", "118"} <= found
    assert "2026" not in found and "35" not in found


def test_collection_marks_blocks_and_writes_a_map(tmp_path):
    m, pages = _collection(tmp_path)
    (m.dir / "book").mkdir()
    (m.dir / "book" / "one.md").write_text("## A finding\n\nFirst para\nwraps.\n\n- item a\n- item b\n")
    (m.dir / "intro.md").write_text("---\ndescription: The dek\n---\n\n# Front\n\nHello.\n")
    (pages / "index.md").write_text(
        "<!-- artoo:source intro.md:1 -->\n---\ndescription: The dek\nlabel: Contents\n---\n\n# Front\n\nHello.\n"
    )
    (pages / "one.md").write_text(
        "---\nlabel: One\n---\n\n<!-- artoo:source book/one.md:1 -->\n# A finding\n\nFirst para\nwraps.\n\n"
        "- item a\n- item b\n\n<!-- artoo:source - -->\n::: html\n<p>made here</p>\n:::\n"
    )
    result = content.render(m)
    assert result.status == "written", result.problems
    data = sourcemap.read(m.dir)
    assert data["contract"] == "artoo-sourcemap/1"
    assert data["files"]["book/one.md"] == hashlib.sha256((m.dir / "book/one.md").read_bytes()).hexdigest()

    one = (m.site_dir / "one.html").read_text()
    title_id = re.search(r'class="article-title" data-artoo-src="(a\d+)"', one).group(1)
    assert _block(data, "one.html", title_id) == {
        "id": title_id, "kind": "title", "file": "book/one.md", "lines": [1, 1]}
    para = _block(data, "one.html", _ids(one, "p")[0])
    assert (para["file"], para["lines"]) == ("book/one.md", [3, 4])
    items = [_block(data, "one.html", i)["lines"] for i in _ids(one, "li")]
    assert items == [[6, 6], [7, 7]]
    assert re.search(r'<p(?![^>]*data-artoo-src)[^>]*>made here</p>', one)  # generated: unmarked
    assert all(b["file"] != "-" for b in data["pages"]["one.html"]["blocks"])

    front = (m.site_dir / "index.html").read_text()
    dek_id = re.search(r'class="article-dek" data-artoo-src="(a\d+)"', front).group(1)
    assert _block(data, "index.html", dek_id)["lines"] == [2, 2]
    brand = re.search(r'class="brand" href="index.html" data-artoo-src="(a\d+)"', front).group(1)
    assert _block(data, "index.html", brand)["key"] == "artifact.title"
    # labels drive navigation; titles stay the page heading
    assert '<a rel="next" href="one.html">One →</a>' in front
    assert '<a rel="prev" href="index.html">← Contents</a>' in one
    assert "<h1 class=\"article-title\"" in one and "A finding</h1>" in one
    assert any(note.startswith("source map:") for note in result.notes)


def test_headings_keep_ids_and_toc_with_marks(tmp_path):
    m, pages = _collection(tmp_path, order=("index.md",))
    (pages / "index.md").write_text("# Front\n\n## Section one\n\nText.\n")
    content.render(m)
    page = (m.site_dir / "index.html").read_text()
    assert re.search(r'<h2 id="section-one" data-artoo-src="a\d+">Section one</h2>', page)
    assert '<a href="#section-one">Section one</a>' in page


def test_without_the_flag_pages_are_unmarked_and_comments_never_render(tmp_path):
    m, pages = _collection(tmp_path, order=("index.md",))
    m.content_sourcemap = False
    (pages / "index.md").write_text("<!-- artoo:source x.md:1 -->\n# Front\n\nText.\n")
    content.render(m)
    page = (m.site_dir / "index.html").read_text()
    assert "data-artoo-src" not in page and "artoo:source" not in page
    assert not (m.dir / sourcemap.MAP_FILE).exists()


def test_article_title_and_masthead_are_mapped(artifact):
    artifact.content_sourcemap = True
    (artifact.dir / artifact.content_source).write_text("# Decision\n\nSupported text.\n")
    content.render(artifact)
    data = sourcemap.read(artifact.dir)
    kinds = {b["kind"]: b for b in data["pages"]["index.html"]["blocks"]}
    assert kinds["title"]["lines"] == [1, 1]
    assert kinds["paragraph"]["lines"] == [3, 3]
    assert kinds["masthead"]["key"] == "artifact.title"


def test_evidence_links_blocks_to_captured_sources_and_claims(tmp_path):
    m, pages = _collection(tmp_path, order=("index.md",))
    receipt = m.dir / "work" / "receipt.json"
    receipt.parent.mkdir(exist_ok=True)
    receipt.write_text('{"share": 28}')
    digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
    (m.dir / "work" / "orphan.json").write_text("{}")
    (pages / "index.md").write_text(
        "---\nevidence: Q20, Q99\n---\n\n# Front\n\n"
        "<!-- artoo:source chapter.md:1 derives=work/receipt.json,work/orphan.json -->\n"
        "The wire ran 28% of its pickups late.\n\nNothing numeric here.\n"
    )
    (m.dir / "chapter.md").write_text("x\n")
    projection = {
        "notebook": {"uid": "nb-1"},
        "sources": [{"id": "F1", "title": "receipt", "sha256": digest}],
        "claims": [
            {"id": "C1", "text": "28% of the wire's pickups came after day 14", "sources": ["F1"]},
            {"id": "C2", "text": "An unrelated 61% share", "sources": ["F9"]},
        ],
        "questions": [{"id": "Q20", "text": "When?"}],
    }
    m.notebook = "nb"
    m.research_publish = False
    (m.dir / "work" / "provenance.json").write_text(json.dumps(projection))
    result = content.render(m)
    assert result.status == "error"
    assert "Q99" in result.problems[0]
    data = sourcemap.read(m.dir)
    page = data["pages"]["index.html"]
    assert page["evidence"] == ["Q20"]
    blocks = [b for b in page["blocks"] if b["kind"] == "paragraph"]
    assert blocks[0]["evidence"] == {
        "sources": ["F1"], "claims": ["C1"], "uncaptured": ["work/orphan.json"]}
    assert "claims" not in blocks[1]["evidence"]
    assert data["evidence"]["uncaptured"] == ["work/orphan.json"]


def test_manifest_round_trips_new_keys(tmp_path):
    m, _pages = _collection(tmp_path, order=("index.md",))
    m.research_publish = False
    m.notebook = "../nb"
    m.edit_config = "production/copycat.json"
    m.edit_comments = "book/comments.json"
    m.save()
    again = manifest.load(m.dir)
    assert again.content_sourcemap and not again.research_publish
    assert (again.edit_config, again.edit_comments) == ("production/copycat.json", "book/comments.json")
    again.edit_status = "site/status.json"
    assert any("edit.status" in p for p in again.validate())
