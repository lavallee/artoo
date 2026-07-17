"""Optional local Vizier guidance with a private, atomic receipt."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .manifest import Manifest

RECEIPT_PATH = Path("work/vizier-guidance.md")


class VizierGuideError(RuntimeError):
    """A local ``vizier guide`` invocation could not produce a receipt."""


def _command(
    executable: str,
    job: str,
    *,
    context: str | None,
    family: str | None,
    series_count: int | None,
    form_count: int | None,
    prior_count: int | None,
    semantic: bool | None,
) -> list[str]:
    args = [executable, "guide", job]
    if context is not None:
        args.extend(["--context", context])
    if family is not None:
        args.extend(["--family", family])
    if series_count is not None:
        args.extend(["--n-series", str(series_count)])
    if form_count is not None:
        args.extend(["--forms", str(form_count)])
    if prior_count is not None:
        args.extend(["--prior", str(prior_count)])
    if semantic is not None:
        args.append("--semantic" if semantic else "--no-semantic")
    return args


def _receipt(m: Manifest, args: list[str], stdout: str, stderr: str) -> str:
    display_args = ["vizier", *args[1:]]
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    text = (
        "# Vizier implementation guidance\n\n"
        "Private working receipt. Artoo keeps this file outside `site/`; it is not deployed.\n\n"
        "## Invocation\n\n"
        f"- Generated: `{generated}`\n"
        f"- Working directory: `{m.dir}`\n"
        f"- Executable: `{args[0]}`\n"
        "- Exit status: `0`\n\n"
        "```text\n"
        f"{shlex.join(display_args)}\n"
        "```\n\n"
        "## Standard output\n\n"
    )
    text += stdout
    if stdout and not stdout.endswith("\n"):
        text += "\n"
    text += "\n## Standard error\n\n"
    text += stderr or "(none)\n"
    if stderr and not stderr.endswith("\n"):
        text += "\n"
    return text


def run_guide(
    m: Manifest,
    job: str,
    *,
    context: str | None = None,
    family: str | None = None,
    series_count: int | None = None,
    form_count: int | None = None,
    prior_count: int | None = None,
    semantic: bool | None = None,
) -> Path:
    """Run the installed ``vizier guide`` and atomically write its private receipt."""
    executable = shutil.which("vizier")
    if executable is None:
        raise VizierGuideError(
            "`vizier` is not available on PATH. Install the keyless CLI with "
            "`uv tool install datavizier` (or activate an existing installation), "
            "then rerun this command. No receipt was written."
        )

    args = _command(
        executable,
        job,
        context=context,
        family=family,
        series_count=series_count,
        form_count=form_count,
        prior_count=prior_count,
        semantic=semantic,
    )
    try:
        result = subprocess.run(
            args,
            cwd=m.dir,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise VizierGuideError(
            f"could not run `vizier guide`: {exc}. Check the local Vizier installation "
            "and rerun this command. No receipt was written."
        ) from exc

    if result.returncode != 0:
        detail = result.stderr or result.stdout or "(vizier produced no diagnostic output)"
        raise VizierGuideError(
            f"`vizier guide` exited with status {result.returncode}. Run the command "
            f"directly to diagnose the local guidance inputs or installation:\n{detail.rstrip()}\n"
            "No receipt was written."
        )

    receipt = m.dir / RECEIPT_PATH
    receipt.parent.mkdir(parents=True, exist_ok=True)
    temporary = receipt.with_name(f".{receipt.name}.tmp")
    try:
        temporary.write_text(
            _receipt(m, args, result.stdout, result.stderr),
            encoding="utf-8",
        )
        temporary.replace(receipt)
    finally:
        temporary.unlink(missing_ok=True)
    return receipt
