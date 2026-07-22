from datetime import date

from artoo import build, manifest as manifest_mod


def test_build_runs_commands(artifact):
    artifact.build_commands = ["echo hello > built.txt"]
    result = build.build(artifact)
    assert result.ok
    assert (artifact.dir / "built.txt").exists()


def test_build_reports_failure(artifact):
    artifact.build_commands = ["false"]
    result = build.build(artifact)
    assert not result.ok
    assert "failed" in result.problems[0]


def test_build_dry_run_runs_nothing(artifact):
    artifact.build_commands = ["echo hi > should-not-exist.txt"]
    result = build.build(artifact, dry_run=True)
    assert result.ok
    assert not (artifact.dir / "should-not-exist.txt").exists()


def test_build_fails_without_index(artifact):
    (artifact.site_dir / "index.html").unlink()
    result = build.build(artifact)
    assert not result.ok


def test_build_stamps_updated(artifact):
    today = date.today().isoformat()
    result = build.build(artifact)
    assert result.ok
    assert result.stamped == today
    assert artifact.updated == today
    # Persisted, not just set in memory — consumers read the file.
    assert manifest_mod.load(artifact.path).updated == today


def test_build_stamp_is_idempotent(artifact):
    build.build(artifact)
    second = build.build(artifact)
    # Already current, so no redundant write and nothing to report.
    assert second.stamped == ""
    assert second.ok


def test_build_dry_run_does_not_stamp(artifact):
    result = build.build(artifact, dry_run=True)
    assert result.stamped == ""
    assert artifact.updated == ""


def test_failed_build_does_not_stamp(artifact):
    artifact.build_commands = ["false"]
    result = build.build(artifact)
    assert not result.ok
    assert result.stamped == ""
    assert artifact.updated == ""
