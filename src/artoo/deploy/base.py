"""Deploy adapter protocol and shared context."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

from ..manifest import Manifest


@dataclass
class DeployContext:
    manifest: Manifest
    staged: Path  # firewall-cleared copy of the site, owned by the caller
    config: dict = field(default_factory=dict)
    dry_run: bool = False

    @property
    def repo_root(self) -> Path | None:
        """Root of the git repo containing the artifact, if any."""
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=self.manifest.dir,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return None
        return Path(proc.stdout.strip())


@dataclass
class DeployResult:
    ok: bool
    message: str
    actions: list[str] = field(default_factory=list)


@runtime_checkable
class Deployer(Protocol):
    name: ClassVar[str]

    def deploy(self, ctx: DeployContext) -> DeployResult: ...
