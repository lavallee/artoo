"""Read-side flip integration, by shelling out to the ``flip`` CLI.

artoo's *write* path (``research.py``) imports flip as a library. The read
path deliberately does not: a site generator wants whatever ``flip`` is on the
user's PATH, not whatever version happens to sit in artoo's own venv. So the
new consumer surfaces — the ``flip-render/1`` JSON projection, the pre-publish
doctor gate, the live notebook vintage — go through ``subprocess`` against the
CLI, discovered on PATH (or pinned via ``ARTOO_FLIP_BIN``) and degrading
gracefully to ``None`` whenever flip is absent, too old, or unhappy. artoo core
must keep working with no flip installed at all.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

#: Environment variable that pins the flip executable (tests, or a user who
#: keeps flip outside PATH). Falls back to ``flip`` discovered on PATH.
FLIP_BIN_ENV = "ARTOO_FLIP_BIN"

_TIMEOUT = 120


def flip_bin() -> str | None:
    """Resolve the flip executable: ``$ARTOO_FLIP_BIN`` first, then PATH."""
    pinned = os.environ.get(FLIP_BIN_ENV)
    if pinned:
        # An explicit pin that does not resolve is a configuration error worth
        # surfacing rather than silently ignoring — but callers treat a missing
        # binary as "flip absent", so only accept a runnable path here.
        if os.path.isabs(pinned):
            return pinned if os.access(pinned, os.X_OK) else None
        return shutil.which(pinned)
    return shutil.which("flip")


def available() -> bool:
    """True when a flip executable can be resolved."""
    return flip_bin() is not None


def _run(nb_dir: Path, args: list[str]) -> subprocess.CompletedProcess | None:
    """Run ``flip <args>`` pinned to ``nb_dir``; None if flip cannot be run.

    Both ``--notebook`` (explicit pin) *and* ``cwd=nb_dir`` are used: flip is
    designed to be run from anywhere inside the notebook, and some subcommands
    (notably ``resolve``) rely on the working directory to locate the enclosing
    workspace even when ``--notebook`` is given. Running with the notebook as
    cwd keeps every subcommand happy; the pin still guarantees the right root.
    """
    binary = flip_bin()
    if binary is None:
        return None
    cwd = str(nb_dir) if nb_dir.is_dir() else None
    try:
        return subprocess.run(
            [binary, "--notebook", str(nb_dir), *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            cwd=cwd,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def export_json(nb_dir: Path, *, include_private: bool = False) -> tuple[dict | None, str]:
    """Return the ``flip-render/1`` projection for ``nb_dir``.

    ``(data, "")`` on success; ``(None, reason)`` otherwise — flip absent, the
    notebook non-public without an opt-in, or malformed output. The projection
    is already policy-filtered by flip; ``include_private`` only adds the flag,
    it never re-filters here.
    """
    args = ["export", "json", "--out", "-"]
    if include_private:
        args.append("--include-private")
    proc = _run(nb_dir, args)
    if proc is None:
        return None, "flip is not installed (or ARTOO_FLIP_BIN does not resolve)"
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "flip export json failed").strip()
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return None, f"flip export json emitted invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "flip export json did not emit an object"
    return data, ""


def doctor_json(nb_dir: Path) -> tuple[list[dict] | None, str]:
    """Return ``flip doctor --json`` findings for ``nb_dir``.

    ``(findings, "")`` on success (``flip doctor`` exits non-zero when it finds
    ERRORs, which is expected and not a failure here); ``(None, reason)`` when
    flip is absent or its output cannot be parsed.
    """
    proc = _run(nb_dir, ["doctor", "--json"])
    if proc is None:
        return None, "flip is not installed (or ARTOO_FLIP_BIN does not resolve)"
    out = proc.stdout.strip()
    if not out:
        # No findings is a legitimate clean result.
        return [], ""
    try:
        findings = json.loads(out)
    except json.JSONDecodeError as exc:
        return None, f"flip doctor --json emitted invalid JSON: {exc}"
    if not isinstance(findings, list):
        return None, "flip doctor --json did not emit a list"
    return findings, ""


def resolve_json(nb_dir: Path, ref: str) -> tuple[dict | None, str]:
    """Resolve a flip reference (``C7``, ``A3``, …) to its entity, as JSON.

    ``(data, "")`` when the id exists in ``nb_dir``; ``(None, reason)`` when flip
    is absent, the id is unknown (flip exits non-zero with a "no page with id"
    message), or the output cannot be parsed. This is the typo-protection the
    feedback verb uses before routing a cited id into the notebook.
    """
    proc = _run(nb_dir, ["resolve", ref, "--json"])
    if proc is None:
        return None, "flip is not installed (or ARTOO_FLIP_BIN does not resolve)"
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or f"flip could not resolve {ref}").strip()
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return None, f"flip resolve emitted invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "flip resolve did not emit an object"
    return data, ""


def question_add(nb_dir: Path, text: str) -> tuple[str | None, str]:
    """Open a flip question in ``nb_dir``; return its allocated ``Q#``.

    ``(qid, "")`` on success — the id is parsed from flip's ``Q<n> open · …``
    confirmation line (``""`` if the line cannot be parsed but the command
    succeeded); ``(None, reason)`` when flip is absent or the command fails.
    This is a *write* into the canonical notebook: the artifact-side feedback
    verb routes reader corrections here rather than editing the render.
    """
    proc = _run(nb_dir, ["question", "add", text])
    if proc is None:
        return None, "flip is not installed (or ARTOO_FLIP_BIN does not resolve)"
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "flip question add failed").strip()
    match = re.search(r"\bQ\d+\b", proc.stdout)
    return (match.group(0) if match else ""), ""


def log_event(nb_dir: Path, text: str) -> tuple[bool, str]:
    """Append one event to ``nb_dir``'s work log (``flip log``).

    ``(True, "")`` on success; ``(False, reason)`` when flip is absent or the
    command fails. The ``--as-log`` route for artifact-side feedback.
    """
    proc = _run(nb_dir, ["log", text])
    if proc is None:
        return False, "flip is not installed (or ARTOO_FLIP_BIN does not resolve)"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "flip log failed").strip()
    return True, ""


def read_vintage(nb_dir: Path) -> dict | None:
    """Read ``{uid, updated}`` from a notebook's ``index.md`` frontmatter.

    This is the *live* notebook manifest (SPEC: the manifest lives in the root
    ``index.md`` frontmatter). Reading it directly needs no flip and honors no
    visibility policy — staleness is a local stamp comparison that must answer
    for internal notebooks too, where ``export json`` would refuse. Returns
    ``None`` when there is no readable notebook there.
    """
    index = nb_dir / "index.md"
    if not index.is_file():
        return None
    try:
        text = index.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    front = text[3:end]
    vintage = {"uid": "", "updated": ""}
    for line in front.splitlines():
        stripped = line.strip()
        for key in ("uid", "updated"):
            prefix = f"{key}:"
            if stripped.startswith(prefix):
                value = stripped[len(prefix):].strip().strip("'\"")
                vintage[key] = value
    if not vintage["uid"] and not vintage["updated"]:
        return None
    return vintage
