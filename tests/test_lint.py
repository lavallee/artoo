"""Design lint: each rule fires on what it names and stays quiet on good work."""

import pytest
from click.testing import CliRunner

from artoo import build, content, docs, lint, scaffold, verify
from artoo.cli import main
from artoo.manifest import KINDS

KIT = '<link rel="stylesheet" href="lib/artoo-kit/components.css">'

# rule -> (pages that must report it, pages that must not). Each is a full
# HTML page or, prefixed "css:", the text of the artifact's own stylesheet.
CASES = {
    "raw-color": (
        [
            '<p style="color:#1f2430">x</p>',
            "<style>.a { background: rgba(0, 0, 0, .5); }</style>",
            "css:.a {\n  border: 1px solid hsl(20 50% 50%);\n}",
        ],
        [
            '<p style="color: var(--text)">x</p>',
            "<style>:root { --brand: #0b5; } .a { color: var(--brand, #0b5); }</style>",
            "css:.a { color: transparent; border-color: currentColor; }",
            'css:.a { fill: url(#fade); content: "#123"; mask-image: linear-gradient(#000, transparent); }',
            "css:@property --x { syntax: '<color>'; initial-value: #fff; inherits: true; }",
        ],
    ),
    "foreign-font": (
        [
            "<style>body { font-family: Inter, sans-serif; }</style>",
            "css:h1 { font-family: Georgia, serif; }",
            "css::root { --font-head: 'Space Grotesk', sans-serif; }",
            "css:.a { font: 700 1.2rem/1.1 Poppins, sans-serif; }",
        ],
        [
            "<style>body { font-family: var(--font-prose); }</style>",
            "css:.a { font-family: var(--serif); font: inherit; }",
            "css::root { --sans: system-ui, 'Segoe UI', Roboto, sans-serif; }",
            "css:@font-face { font-family: 'Inter'; src: url(inter.woff2); }",
        ],
    ),
    "gradient-text": (
        [
            "<style>h1 { -webkit-background-clip: text; background-clip: text; }</style>",
        ],
        [
            "<style>.a { background-clip: padding-box; }</style>",
        ],
    ),
    "glass": (
        [
            "<style>.panel { background: rgb(255 255 255 / 40%); backdrop-filter: blur(12px); }</style>",
        ],
        [
            "<style>.bar { position: sticky; top: 0; backdrop-filter: blur(8px); }</style>",
            "css:.m { background: color-mix(in srgb, var(--bg) 94%, transparent);"
            " backdrop-filter: blur(12px); }",
            "css:dialog::backdrop { backdrop-filter: blur(3px); }",
            "css:.a { backdrop-filter: blur(0); }",
        ],
    ),
    "emoji-icon": (
        [
            "<h2>🚀 Launch</h2>",
            "<ul><li>⚠️ Watch this</li></ul>",
            '<nav><a href="a.html">📊 Data</a></nav>',
            "<button>✅ Done</button>",
        ],
        [
            "<ul><li>✓ checked</li><li>→ next</li><li>★ starred</li></ul>",
            "<h2>Launch 🚀</h2>",
            "<p>🚀 a paragraph may start however it likes</p>",
            '<a href="a.html">📊 a link outside nav</a>',
        ],
    ),
    "numbered-eyebrow": (
        [
            '<div><span class="index">01</span><h3>First</h3></div>',
            "<p>02 —</p>",
            "<h2>03. The method</h2>",
            "<h3>04 · Classify</h3>",
        ],
        [
            "<table><tr><th>Month</th></tr><tr><td>01</td></tr></table>",
            "<h2>2024 results</h2>",
            "<p>1</p><span>12</span>",
            "<ol><li>First</li><li>Second</li></ol>",
            "<h1>03 · Copywriting canon</h1>",
            '<a href="assessments/03.html"><h3>03 · Copywriting canon</h3></a>',
            '<div class="stat"><b>00</b><span>placeholder figure</span></div>',
        ],
    ),
    "card-as-container": (
        [
            '<div class="nav-card"><h3>Facts</h3><p>Just text.</p></div>',
            f'{KIT}<div class="card"><h3>Facts</h3></div>',
        ],
        [
            '<a class="nav-card" href="a.html"><h3>Go</h3></a>',
            '<div class="nav-card"><h3><a href="a.html">Go</a></h3></div>',
            '<div class="card"><h3>Own class, no kit</h3></div>',
        ],
    ),
    "stock-copy": (
        [
            "<p>Let us delve into the data.</p>",
            "<p>In today’s fast-paced world, data matters.</p>",
            "<p>It promises seamless integration with your tools.</p>",
            "<p>It's not just a report, it's a movement.</p>",
            "<p>The result is a testament to the team.</p>",
        ],
        [
            "<p>Resume recovery is less seamless than on macOS.</p>",
            "<p>We read 40 filings and checked each total.</p>",
            "<pre><code>delve()</code></pre>",
        ],
    ),
}


def _lint(case: str):
    if case.startswith("css:"):
        return lint.lint_css(case[4:])
    return lint.lint_html(f"<!doctype html><html><head></head><body>{case}</body></html>")


def test_every_rule_has_a_positive_and_a_negative_case():
    assert set(CASES) == set(lint.RULES)
    for rule, (positives, negatives) in CASES.items():
        assert positives and negatives, rule


@pytest.mark.parametrize(
    "rule,case",
    [(rule, case) for rule, (positives, _) in CASES.items() for case in positives],
)
def test_rule_reports_what_it_names(rule, case):
    assert rule in {hit[1] for hit in _lint(case)}


@pytest.mark.parametrize(
    "rule,case",
    [(rule, case) for rule, (_, negatives) in CASES.items() for case in negatives],
)
def test_rule_stays_quiet_on_good_work(rule, case):
    assert rule not in {hit[1] for hit in _lint(case)}


def test_every_rule_is_documented_with_its_fix():
    result = CliRunner().invoke(main, ["docs", "verify"])
    assert result.exit_code == 0
    assert docs.LINT_RULES_PLACEHOLDER not in result.output
    for rule in lint.RULES.values():
        assert f"| `{rule.id}` |" in result.output


def _page(artifact, body, name="index.html"):
    artifact.content_source = ""
    artifact.save()
    (artifact.site_dir / name).write_text(
        f"<!doctype html><html><head></head><body>\n{body}\n</body></html>", encoding="utf-8"
    )


def test_findings_name_file_line_rule_and_fix(artifact):
    _page(artifact, "<p>ok</p>\n<h2>🚀 Launch</h2>")
    (artifact.site_dir / "theme.css").write_text(".a {\n  color: #123456;\n}\n")
    messages = [finding.message() for finding in lint.check(artifact)]
    assert any(m.startswith("site/index.html:3 [emoji-icon]") for m in messages)
    assert any(
        m.startswith("site/theme.css:2 [raw-color] color: #123456 — use a kit token")
        for m in messages
    )


def test_vendored_libraries_are_never_linted(artifact):
    _page(artifact, "<p>ok</p>")
    (artifact.site_dir / "lib" / "artoo-kit" / "extra.css").write_text(".x{color:#fff}")
    assert lint.check(artifact) == []


def test_hits_are_capped_per_file_and_per_artifact(artifact):
    styles = "".join(f'<p style="color:#00000{i}">x</p>' for i in range(8))
    _page(artifact, styles)
    for n in range(7):
        _page(artifact, styles, name=f"p{n}.html")
    found = [f for f in lint.check(artifact) if f.rule == "raw-color"]
    files = {f.path for f in found if f.line}
    assert len(files) == lint.FILE_CAP
    assert all(sum(f.path == path for f in found) == lint.CAP for path in files)
    assert "(and 5 more in this file)" in found[lint.CAP - 1].message()
    assert found[-1].message().startswith("site/ [raw-color] 24 more in 3 other files")


def test_lint_warns_in_verify_and_build_but_never_fails(artifact):
    _page(artifact, '<h2>🚀 Launch</h2><div class="nav-card">text</div>')
    result = verify.static(artifact)
    assert result.ok
    assert any("[emoji-icon]" in w for w in result.warnings)
    assert any("[card-as-container]" in w for w in result.warnings)
    built = build.build(artifact)
    assert built.ok, built.problems
    assert any("[emoji-icon]" in w for w in built.warnings)


def test_verify_json_lists_lint_findings_as_warnings(artifact):
    _page(artifact, "<h2>🚀 Launch</h2>")
    result = CliRunner().invoke(main, ["verify", str(artifact.dir), "--json"])
    assert result.exit_code == 0, result.output
    assert '[emoji-icon]' in result.output


def test_allow_skips_a_rule_and_an_unknown_id_is_a_problem(artifact):
    _page(artifact, "<h2>🚀 Launch</h2><p>Let us delve in.</p>")
    artifact.verify_allow = ["emoji-icon"]
    rules = {f.rule for f in lint.check(artifact)}
    assert rules == {"stock-copy"}

    artifact.verify_allow = ["emoji"]
    result = verify.static(artifact)
    assert not result.ok
    (problem,) = [p for p in result.problems if "verify.allow" in p]
    assert "'emoji'" in problem and "emoji-icon" in problem and "raw-color" in problem
    artifact.save()
    assert not build.build(artifact).ok


MARKDOWN = """# The decision

A plain lede paragraph with **bold**, *emphasis*, and `code`.

## Evidence

- one point
- another point, with a [link](https://example.com)

1. first
2. second

| year | value |
|---:|---|
| 2024 | 12 |
| 2025 | 14 |

> A quotation.

```python
print("hello")
```

### A smaller heading

Closing text.
"""


def test_pages_artoo_renders_from_markdown_are_clean(artifact):
    (artifact.dir / artifact.content_source).write_text(MARKDOWN)
    assert content.render(artifact).status == "written"
    assert [f.message() for f in lint.check(artifact)] == []


@pytest.mark.parametrize("kind", KINDS)
def test_freshly_scaffolded_artifacts_are_clean(tmp_path, kind):
    m = scaffold.init_artifact(tmp_path / "a", title="A", kind=kind)
    content.render(m)
    assert [f.message() for f in lint.check(m)] == []
