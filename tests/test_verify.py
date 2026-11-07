import builtins
import json

import pytest
from click.testing import CliRunner

from artoo import build, verify
from artoo.cli import main


def _without_playwright(monkeypatch):
    real_import = builtins.__import__

    def without(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without)


def _raw(artifact, html):
    artifact.content_source = ""
    artifact.save()
    (artifact.site_dir / "index.html").write_text(html)


def test_static_reports_missing_files_anchors_duplicate_ids_and_remote_runtime(artifact):
    _raw(
        artifact,
        '<!doctype html><html><head><script src="https://x.test/app.js"></script></head>'
        '<body><div id="same"></div><div id="same"></div>'
        '<a href="missing.html#nope">Missing</a></body></html>',
    )
    problems = verify.static(artifact).problems
    assert any("repeats id" in problem for problem in problems)
    assert any("loads https://x.test" in problem for problem in problems)
    assert any("references missing" in problem for problem in problems)


def test_static_warns_without_turning_review_prompts_into_failures(artifact):
    _raw(
        artifact,
        '<!doctype html><html><body><img src="lib/artoo-kit/favicon.svg">'
        '<table><tr><td>A</td></tr></table><a href="#">Go</a></body></html>',
    )
    result = verify.static(artifact)
    assert result.ok
    assert any("without alt" in warning for warning in result.warnings)
    assert any("no <th>" in warning for warning in result.warnings)
    assert any("nowhere-pointing" in warning for warning in result.warnings)


def test_static_rejects_private_and_missing_css_dependencies(artifact):
    private = artifact.dir / "work" / "private.png"
    private.write_bytes(b"private")
    css = artifact.site_dir / "theme.css"
    css.write_text('.one { background: url("missing.png"); }')
    _raw(
        artifact,
        '<!doctype html><html><head><link rel="stylesheet" href="theme.css"></head>'
        '<body><img alt="" src="../work/private.png"></body></html>',
    )
    problems = verify.static(artifact).problems
    assert any("outside build.site" in problem for problem in problems)
    assert any("missing CSS resource" in problem for problem in problems)


def test_static_treats_firewall_withheld_targets_as_missing_from_publish(artifact):
    hidden = artifact.site_dir / "_draft"
    hidden.mkdir()
    (hidden / "notes.html").write_text("private")
    _raw(
        artifact,
        '<!doctype html><html><body><a href="_draft/notes.html">Notes</a></body></html>',
    )
    problems = verify.static(artifact).problems
    assert any("firewall-withheld" in problem for problem in problems)


def test_browser_is_an_actionable_soft_dependency(artifact, monkeypatch):
    _without_playwright(monkeypatch)
    result = verify.browser(artifact)
    assert not result.ok
    assert "Playwright" in result.problems[0]
    assert "playwright install chromium" in result.problems[0]


def test_optional_browser_without_playwright_is_a_note_not_a_problem(artifact, monkeypatch):
    _without_playwright(monkeypatch)
    result = verify.browser(artifact, optional=True)
    assert result.ok
    assert "Playwright is not installed" in result.skipped
    assert "--with-executables-from playwright" in result.skipped


# ---- message formatting ----------------------------------------------------


def _probe(**rules):
    data = {"overflow": None, "counts": {}}
    for rule, items in rules.items():
        if rule == "overflow":
            data["overflow"] = items
            continue
        data[rule] = items
        data["counts"][rule] = len(items)
    return data


def test_findings_name_page_viewport_selector_heading_and_source():
    item = {"sel": "section.card > p", "heading": "methods", "src": "content.md:42",
            "text": "Quarterly totals"}
    problems, warnings = verify.findings_from_probe(
        "index.html", {"phone": _probe(clipped=[item])}
    )
    assert not problems
    assert warnings == [
        'index.html (phone) text is clipped by its box: "Quarterly totals" at '
        "`section.card > p` §methods content.md:42; give the box room or let the text wrap"
    ]


def test_findings_at_both_widths_are_one_message():
    item = {"sel": "p.note", "heading": "", "src": "", "ratio": 2.5, "need": 4.5,
            "fg": "#999999", "bg": "#ffffff", "text": "faint"}
    _, warnings = verify.findings_from_probe(
        "index.html", {"phone": _probe(contrast=[item]), "desktop": _probe(contrast=[item])}
    )
    assert len(warnings) == 1
    assert warnings[0].startswith("index.html (phone, desktop) contrast 2.5:1 is under 4.5:1")


def test_findings_cap_at_three_per_rule_and_count_the_rest():
    items = [{"sel": f"img:nth-of-type({i})", "detail": f"{i}.png"} for i in range(1, 6)]
    data = _probe(image=items)
    data["counts"]["image"] = 50  # the probe keeps a sample; its count is the truth
    problems, warnings = verify.findings_from_probe("a.html", {"phone": data})
    assert not warnings
    assert len(problems) == verify.CAP + 1
    assert problems[-1] == "a.html (phone) and 47 more image finding(s)"


def test_overflow_names_the_widest_offenders():
    overflow = {
        "width": 916, "viewport": 390, "total": 4,
        "offenders": [
            {"sel": "div.wide", "heading": "data", "src": "", "right": 916},
            {"sel": "table", "heading": "", "src": "content.md:9", "right": 600},
        ],
    }
    problems, _ = verify.findings_from_probe("index.html", {"phone": _probe(overflow=overflow)})
    assert problems == [
        "index.html overflows horizontally at 390px (phone): the page is 916px wide; widest: "
        "`div.wide` §data reaches 916px, `table` content.md:9 reaches 600px, and 2 more; "
        "let it wrap, or put wide content in a scroll region (`article-table`)"
    ]


def test_warnings_never_fail_and_problems_always_do():
    assert {rule for rule, (fails, _) in verify.RULES.items() if fails} == {
        "overflow", "image", "diagram",
    }


# ---- build policy ------------------------------------------------------------


def test_build_api_never_launches_a_browser_unless_asked(artifact, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("build() launched a browser by default")

    monkeypatch.setattr(verify, "browser", boom)
    result = build.build(artifact)
    assert result.ok
    assert result.browser == ""


def test_auto_policy_without_playwright_notes_the_skip(artifact, monkeypatch):
    _without_playwright(monkeypatch)
    result = build.build(artifact, browser="auto")
    assert result.ok
    assert result.browser.startswith("browser checks skipped: Playwright is not installed")
    assert 'set [verify] browser = "never"' in result.browser
    assert result.contact_sheet == ""


def test_always_policy_without_playwright_is_a_problem(artifact, monkeypatch):
    _without_playwright(monkeypatch)
    result = build.build(artifact, browser="always")
    assert not result.ok
    assert any(
        "Playwright" in p and "--no-browser" in p and '"auto"' in p for p in result.problems
    )
    assert result.stamped == ""


def test_never_policy_skips_silently(artifact, monkeypatch):
    _without_playwright(monkeypatch)
    result = build.build(artifact, browser="never")
    assert result.ok
    assert result.browser == ""


def test_browser_checks_wait_for_static_checks(artifact, monkeypatch):
    monkeypatch.setattr(verify, "browser", lambda *a, **k: pytest.fail("browser ran"))
    _raw(artifact, '<!doctype html><html><body><a href="missing.html">x</a></body></html>')
    result = build.build(artifact, browser="always")
    assert not result.ok
    assert "skipped until the problems above are fixed" in result.browser


def test_verification_dir_is_never_published(artifact):
    assert build.verification_dir(artifact) == artifact.dir / "work" / "verification"
    artifact.site = "."
    target = build.verification_dir(artifact)
    assert not verify.firewall.is_publishable(target.relative_to(artifact.dir) / "x.png")


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, m, **kwargs):
        self.calls.append(kwargs)
        result = verify.VerificationResult(pages=1)
        sheet = kwargs["screenshots"] / "contact-sheet.png"
        result.contact_sheet = sheet
        return result


@pytest.mark.parametrize(
    ("manifest", "flags", "expected"),
    [
        ("auto", [], {"optional": True}),
        ("never", [], None),
        ("always", [], {"optional": False}),
        ("never", ["--browser"], {"optional": False}),
        ("auto", ["--no-browser"], None),
        ("always", ["--no-browser"], None),
    ],
)
def test_cli_flags_override_the_manifest_policy(artifact, monkeypatch, manifest, flags, expected):
    artifact.verify_browser = manifest
    artifact.save()
    recorder = _Recorder()
    monkeypatch.setattr(verify, "browser", recorder)
    result = CliRunner().invoke(main, ["build", str(artifact.dir), "--json", *flags])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    if expected is None:
        assert recorder.calls == []
        assert report["browser"] == ""
        assert report["contact_sheet"] == ""
    else:
        assert recorder.calls[0]["optional"] is expected["optional"]
        assert recorder.calls[0]["screenshots"] == artifact.dir / "work" / "verification"
        assert report["browser"].startswith("browser checks: 1 page(s)")
        assert report["contact_sheet"].endswith("work/verification/contact-sheet.png")


def test_cli_build_points_at_the_contact_sheet(artifact, monkeypatch):
    monkeypatch.setattr(verify, "browser", _Recorder())
    result = CliRunner().invoke(main, ["build", str(artifact.dir), "--browser"])
    assert result.exit_code == 0, result.output
    assert "look once: work/verification/contact-sheet.png" in result.output


def test_static_fails_a_diagram_page_with_no_renderer(artifact):
    _raw(artifact, '<!doctype html><html><body><pre class="mermaid">graph LR\nA-->B</pre></body></html>')
    problems = verify.static(artifact).problems
    assert any(
        "1 Mermaid block(s)" in problem and "artoo lib add artoo-diagrams" in problem
        for problem in problems
    )


def test_static_names_the_one_missing_diagram_script(artifact):
    from artoo import libraries

    libraries.add(artifact, "artoo-diagrams")
    _raw(
        artifact,
        '<!doctype html><html><body><pre><code class="language-mermaid">graph LR\nA-->B'
        '</code></pre><script src="lib/artoo-diagrams/diagrams.js"></script></body></html>',
    )
    problems = [p for p in verify.static(artifact).problems if "Mermaid" in p]
    assert len(problems) == 1
    assert "lib/artoo-diagrams/pele.global.js" in problems[0]
    assert "diagrams.js or" not in problems[0]


def test_static_accepts_either_diagram_renderer(artifact):
    from artoo import libraries

    libraries.add(artifact, "artoo-diagrams")
    _raw(
        artifact,
        '<!doctype html><html><body><pre class="mermaid">graph LR\nA-->B</pre>'
        '<script src="lib/artoo-diagrams/pele.global.js"></script>'
        '<script src="lib/artoo-diagrams/diagrams.js"></script></body></html>',
    )
    assert not [p for p in verify.static(artifact).problems if "Mermaid" in p]
    (artifact.site_dir / "lib" / "vendor").mkdir(parents=True)
    (artifact.site_dir / "lib" / "vendor" / "mermaid.min.js").write_text("")
    _raw(
        artifact,
        '<!doctype html><html><body><pre class="mermaid">graph LR\nA-->B</pre>'
        '<script src="lib/vendor/mermaid.min.js"></script></body></html>',
    )
    assert not [p for p in verify.static(artifact).problems if "Mermaid" in p]


# ---- real Chromium -----------------------------------------------------------
# These run where Playwright and its Chromium are installed:
#   uv run --with playwright pytest -q tests/test_verify.py


@pytest.fixture
def chromium():
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        with sync_api.sync_playwright() as playwright:
            playwright.chromium.launch().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium does not launch here: {exc}")


DIRTY = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Dirty</title>
<style>
body{font:16px/1.5 sans-serif;margin:0;padding:16px;background:#fff;color:#222}
.wide{width:900px}
.scroller{overflow-x:auto}.scroller div{width:2000px}
.clip{display:inline-block;width:120px;height:1.5em;overflow:hidden;white-space:nowrap}
.ellipsis{width:120px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.tiny{font-size:10px}
.faint{color:#bbb}
.large{color:#888;font-size:28px}
.stage{position:relative}
.badge{position:absolute;top:0;left:0;background:#fff}
.sr-only{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0,0,0,0)}
.hero{background-image:linear-gradient(#000,#333);color:#444}
</style></head><body>
<h1 id="top">Dirty</h1>
<h2 id="methods">Methods</h2>
<div data-src="content.md:42"><p><span class="clip">This sentence is far too long for its box</span></p></div>
<p class="ellipsis">This sentence is too long but ellipsed on purpose</p>
<p class="tiny">Tiny footnote text</p>
<p class="faint">Faint grey text on white</p>
<p class="large">Large grey text passes at 3:1</p>
<p class="hero">Text on a gradient is not judged</p>
<p>Separated <span class="faint">·</span> by an ornament</p>
<span class="sr-only">Screen reader text</span>
<div class="stage"><p>Underlying paragraph text here</p><span class="badge">Badge over it</span></div>
<img src="broken.png" alt="not really a picture">
<div class="scroller"><div>scrolls inside its own region</div></div>
<h2 id="data">Data</h2>
<div class="wide">a box that is too wide for a phone</div>
<pre class="mermaid">graph LR
A--&gt;B</pre>
<script src="lib/vendor/mermaid.min.js"></script>
</body></html>
"""


def test_browser_checks_find_each_fault_and_say_where(artifact, chromium):
    _raw(artifact, DIRTY)
    (artifact.site_dir / "broken.png").write_text("not an image")
    vendor = artifact.site_dir / "lib" / "vendor"
    vendor.mkdir(parents=True)
    (vendor / "mermaid.min.js").write_text("/* a renderer that never renders */")
    assert verify.static(artifact).ok  # every fault below is one only a browser sees

    result = verify.browser(artifact)
    problems = "\n".join(result.problems)
    warnings = "\n".join(result.warnings)

    assert "index.html overflows horizontally at 390px (phone)" in problems
    assert "`div.wide` §data reaches" in problems
    assert "at 1440px" not in problems
    assert "broken image 'broken.png' at `img` §methods" in problems
    assert "Mermaid diagram did not render" in problems and "§data" in problems

    assert 'text is clipped by its box: "This sentence' in warnings
    assert "span.clip` §methods content.md:42" in warnings
    assert '10px text "Tiny footnote text"' in warnings
    assert "(#bbbbbb on #ffffff)" in warnings
    assert 'positioned text "Badge over it" sits over `div.stage > p`' in warnings

    for quiet in ("ellipsed", "Large grey", "gradient", "Screen reader", "scrolls inside", "·"):
        assert quiet not in problems + warnings, quiet


def test_build_runs_browser_checks_and_writes_one_contact_sheet(artifact, chromium):
    source = artifact.dir / artifact.content_source
    source.write_text(
        source.read_text() + "\n\n## Flow\n\n```mermaid\ngraph LR\n  A --> B\n```\n"
    )
    result = build.build(artifact, browser="always")
    assert result.ok, result.problems
    assert not [w for w in result.warnings if "(phone" in w or "(desktop" in w], result.warnings
    assert result.browser.startswith("browser checks: 1 page(s) at phone and desktop width")
    sheet = artifact.dir / "work" / "verification" / "contact-sheet.png"
    assert result.contact_sheet == str(sheet)
    assert sheet.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert (sheet.parent / "index-phone.png").is_file()
    assert (sheet.parent / "index-desktop.png").is_file()


def test_verify_screenshots_dir_gets_the_contact_sheet(artifact, chromium, tmp_path):
    shots = tmp_path / "shots"
    result = CliRunner().invoke(
        main, ["verify", str(artifact.dir), "--browser", "--screenshots", str(shots)]
    )
    assert result.exit_code == 0, result.output
    assert (shots / "contact-sheet.png").is_file()
    assert "look once:" in result.output
