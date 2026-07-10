"""Build an artifact: run its refresh commands, then verify the site."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from . import firewall
from .manifest import Manifest


@dataclass
class BuildResult:
    ok: bool
    ran: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    withheld: list[str] = field(default_factory=list)


def build(m: Manifest, *, dry_run: bool = False) -> BuildResult:
    """Run ``[build] commands`` from the artifact directory, then firewall-check.

    Build commands refresh generated inputs (exports, data snapshots). They
    run with the artifact directory as cwd so relative paths in the manifest
    stay portable.
    """
    result = BuildResult(ok=True)
    for command in m.build_commands:
        result.ran.append(command)
        if dry_run:
            continue
        proc = subprocess.run(
            command, shell=True, cwd=m.dir, capture_output=True, text=True
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            result.ok = False
            result.problems.append(
                f"build command failed ({proc.returncode}): {command}\n{detail}"
            )
            return result

    result.problems.extend(firewall.check(m))
    if result.problems:
        result.ok = False
    result.withheld = [str(p) for p in firewall.withheld(m.site_dir)] if m.site_dir.is_dir() else []
    return result
