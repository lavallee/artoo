from artoo import workers


def test_defaults():
    assert workers.resolve("analysis") == "codex"
    assert workers.resolve("synthesis") == "claude"
    assert workers.resolve("unknown-role") == "claude"


def test_manifest_overrides():
    overrides = {"analysis": "claude", "synthesis": {"worker": "codex", "model": "o3"}}
    assert workers.resolve("analysis", overrides) == "claude"
    assert workers.resolve("synthesis", overrides) == "codex"
    assert workers.resolve_model("synthesis", overrides) == "o3"
    assert workers.resolve_model("analysis", overrides) == ""


def test_env_wins(monkeypatch):
    monkeypatch.setenv("ARTOO_WORKER_ANALYSIS", "my-tool")
    assert workers.resolve("analysis", {"analysis": "codex"}) == "my-tool"


def test_disabled_makes_unavailable():
    # conftest sets ARTOO_WORKERS_DISABLED=1
    assert not workers.is_available("codex")
    assert not workers.is_available("claude")


def test_run_unavailable_returns_error():
    result = workers.run("analysis", "hi")
    assert not result.ok
    assert "not available" in result.error


def test_generic_worker(monkeypatch, tmp_path):
    monkeypatch.delenv("ARTOO_WORKERS_DISABLED", raising=False)
    script = tmp_path / "echo-worker"
    script.write_text("#!/bin/sh\ncat\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=":")
    result = workers.run("analysis", "ping", overrides={"analysis": "echo-worker"})
    assert result.ok
    assert result.text == "ping"


def test_empty_output_is_an_error(monkeypatch, tmp_path):
    monkeypatch.delenv("ARTOO_WORKERS_DISABLED", raising=False)
    script = tmp_path / "silent-worker"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=":")
    result = workers.run("analysis", "ping", overrides={"analysis": "silent-worker"})
    assert not result.ok
