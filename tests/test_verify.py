from artoo import verify


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
    import builtins

    real_import = builtins.__import__

    def without_playwright(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_playwright)
    result = verify.browser(artifact)
    assert not result.ok
    assert "Playwright" in result.problems[0]
