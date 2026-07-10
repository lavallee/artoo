"""Workers: tiered delegation to local agent CLIs.

artoo core makes no model API calls and holds no keys. Generators do model
work through *workers* — shell-outs to agent CLIs the user already has and
has already authenticated. Two roles cover the common split:

- ``analysis`` — high-volume, per-unit fan-out. Default: ``codex`` (cheap,
  reads the repo itself inside a read-only sandbox).
- ``synthesis`` — narrative, structure, judgment. Default: ``claude``.

Overrides, most specific wins: ``ARTOO_WORKER_<ROLE>`` env var, then the
manifest's ``[workers]`` table, then defaults. Set ``ARTOO_WORKERS_DISABLED=1``
to force every worker unavailable (used by tests and degraded runs).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROLES = {
    "analysis": "codex",
    "synthesis": "claude",
}

DEFAULT_TIMEOUT = 600


@dataclass
class WorkerResult:
    ok: bool
    text: str = ""
    error: str = ""


def resolve(role: str, overrides: dict | None = None) -> str:
    """Resolve a role to a worker name (``codex``/``claude``/custom command)."""
    env = os.environ.get(f"ARTOO_WORKER_{role.upper()}")
    if env:
        return env
    if overrides and role in overrides:
        value = overrides[role]
        return value.get("worker", "") if isinstance(value, dict) else str(value)
    return DEFAULT_ROLES.get(role, "claude")


def resolve_model(role: str, overrides: dict | None = None) -> str:
    if overrides and isinstance(overrides.get(role), dict):
        return overrides[role].get("model", "")
    return ""


def is_available(worker: str) -> bool:
    if os.environ.get("ARTOO_WORKERS_DISABLED"):
        return False
    return shutil.which(worker) is not None


def run(
    role: str,
    prompt: str,
    *,
    cwd: Path | None = None,
    overrides: dict | None = None,
    model: str = "",
    timeout: int = DEFAULT_TIMEOUT,
) -> WorkerResult:
    """Run a prompt through the worker for ``role``; returns its final text."""
    worker = resolve(role, overrides)
    model = model or resolve_model(role, overrides)
    if not is_available(worker):
        return WorkerResult(ok=False, error=f"worker {worker!r} not available on PATH")

    if worker == "codex":
        return _run_codex(prompt, cwd=cwd, model=model, timeout=timeout)
    if worker == "claude":
        return _run_claude(prompt, cwd=cwd, model=model, timeout=timeout)
    return _run_generic(worker, prompt, cwd=cwd, timeout=timeout)


def _finish(proc: subprocess.CompletedProcess, text: str) -> WorkerResult:
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-2000:]
        return WorkerResult(ok=False, error=f"worker exited {proc.returncode}: {detail}")
    if not text.strip():
        return WorkerResult(ok=False, error="worker returned empty output")
    return WorkerResult(ok=True, text=text.strip())


def _run_codex(prompt: str, *, cwd: Path | None, model: str, timeout: int) -> WorkerResult:
    """codex exec: non-interactive, read-only sandbox, runs *inside* the target
    directory so the model can read files itself instead of us inlining them."""
    with tempfile.NamedTemporaryFile(mode="r", suffix=".md", delete=False) as out:
        out_path = Path(out.name)
    cmd = [
        "codex", "exec",
        "--sandbox", "read-only",
        "--skip-git-repo-check",
        "--output-last-message", str(out_path),
    ]
    if model:
        cmd += ["--model", model]
    if cwd:
        cmd += ["-C", str(cwd)]
    cmd.append(prompt)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        text = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
        return _finish(proc, text)
    except subprocess.TimeoutExpired:
        return WorkerResult(ok=False, error=f"codex timed out after {timeout}s")
    finally:
        out_path.unlink(missing_ok=True)


def _run_claude(prompt: str, *, cwd: Path | None, model: str, timeout: int) -> WorkerResult:
    cmd = ["claude", "-p"]
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            timeout=timeout, cwd=cwd,
        )
        return _finish(proc, proc.stdout)
    except subprocess.TimeoutExpired:
        return WorkerResult(ok=False, error=f"claude timed out after {timeout}s")


def _run_generic(worker: str, prompt: str, *, cwd: Path | None, timeout: int) -> WorkerResult:
    """Any other worker: a command that takes the prompt on stdin, answers on stdout."""
    try:
        proc = subprocess.run(
            [worker], input=prompt, capture_output=True, text=True,
            timeout=timeout, cwd=cwd,
        )
        return _finish(proc, proc.stdout)
    except subprocess.TimeoutExpired:
        return WorkerResult(ok=False, error=f"{worker} timed out after {timeout}s")
