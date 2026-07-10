"""The escape-hatch adapter: publish with an arbitrary command.

The command runs from the artifact directory with the staged (firewall-
cleared) site exposed via environment variables. Whatever bespoke pipeline
already exists — ssh scripts, CI triggers, cloud CLIs — works today.
"""

from __future__ import annotations

import os
import subprocess
from typing import ClassVar

from .base import DeployContext, DeployResult


class CommandDeployer:
    name: ClassVar[str] = "command"

    def deploy(self, ctx: DeployContext) -> DeployResult:
        command = ctx.config.get("run", "")
        if not command:
            return DeployResult(
                ok=False,
                message='command adapter needs [deploy.command] run = "<shell command>"',
            )
        env = os.environ.copy()
        env.update(
            {
                "ARTOO_SITE_DIR": str(ctx.staged),
                "ARTOO_SLUG": ctx.manifest.slug,
                "ARTOO_ARTIFACT_DIR": str(ctx.manifest.dir),
                "ARTOO_REPO_ROOT": str(ctx.repo_root or ""),
            }
        )
        if ctx.dry_run:
            return DeployResult(
                ok=True,
                message="dry run — command not executed",
                actions=[f"would run: {command}"],
            )
        proc = subprocess.run(
            command, shell=True, cwd=ctx.manifest.dir, env=env,
            capture_output=True, text=True,
        )
        output = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0:
            return DeployResult(
                ok=False,
                message=f"publish command exited {proc.returncode}",
                actions=[command, output],
            )
        return DeployResult(ok=True, message="published", actions=[command, output])
