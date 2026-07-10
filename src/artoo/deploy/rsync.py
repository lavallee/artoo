"""rsync/ssh deploys to named targets.

Target definitions (hosts, users, paths, keys) are local configuration and
never enter the repo: they live in ``~/.config/artoo/targets.toml``, with a
git-ignored ``.artoo/targets.toml`` at the repo root taking precedence.

Example targets file::

    [targets.public]
    host = "static.example.com"
    user = "deploy"
    path = "/var/www/static"
    ssh_key = "~/.ssh/deploy_ed25519"   # optional
    port = 22                            # optional

The artifact manifest names the target, never the credentials::

    [deploy.rsync]
    target = "public"
    subpath = "reports/q3"   # default: the artifact slug
"""

from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path
from typing import ClassVar

from .base import DeployContext, DeployResult


def targets_files(repo_root: Path | None) -> list[Path]:
    files = []
    if repo_root:
        files.append(repo_root / ".artoo" / "targets.toml")
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    files.append(config_home / "artoo" / "targets.toml")
    return files


def load_targets(repo_root: Path | None) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    # User-level first so repo-level entries override on collision.
    for path in reversed(targets_files(repo_root)):
        if not path.is_file():
            continue
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        for name, target in data.get("targets", {}).items():
            merged[name] = dict(target)
    return merged


def build_command(target: dict, staged: Path, subpath: str, *, dry_run: bool) -> list[str]:
    ssh_parts = ["ssh", "-o", "StrictHostKeyChecking=accept-new"]
    if target.get("ssh_key"):
        ssh_parts += ["-i", str(Path(target["ssh_key"]).expanduser())]
    if target.get("port"):
        ssh_parts += ["-p", str(target["port"])]

    remote_path = target["path"].rstrip("/")
    if subpath:
        remote_path = f"{remote_path}/{subpath.strip('/')}"

    cmd = ["rsync", "-avz", "--delete", "--mkpath", "-e", " ".join(ssh_parts)]
    if dry_run:
        cmd.append("--dry-run")
    cmd.append(f"{staged}/")
    cmd.append(f"{target['user']}@{target['host']}:{remote_path}/")
    return cmd


class RsyncDeployer:
    name: ClassVar[str] = "rsync"

    def deploy(self, ctx: DeployContext) -> DeployResult:
        target_name = ctx.config.get("target", "")
        if not target_name:
            return DeployResult(
                ok=False,
                message='rsync adapter needs [deploy.rsync] target = "<name>"',
            )
        targets = load_targets(ctx.repo_root)
        if target_name not in targets:
            searched = ", ".join(str(p) for p in targets_files(ctx.repo_root))
            return DeployResult(
                ok=False,
                message=(
                    f"no rsync target named {target_name!r}. "
                    f"Define it under [targets.{target_name}] in one of: {searched}"
                ),
            )
        target = targets[target_name]
        missing = [k for k in ("host", "user", "path") if not target.get(k)]
        if missing:
            return DeployResult(
                ok=False,
                message=f"target {target_name!r} is missing: {', '.join(missing)}",
            )

        subpath = ctx.config.get("subpath", ctx.manifest.slug)
        cmd = build_command(target, ctx.staged, subpath, dry_run=ctx.dry_run)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return DeployResult(
                ok=False,
                message=f"rsync exited {proc.returncode}",
                actions=[" ".join(cmd), proc.stderr.strip()],
            )
        verb = "dry run — would sync" if ctx.dry_run else "synced"
        return DeployResult(
            ok=True,
            message=f"{verb} to {target['host']}",
            actions=[" ".join(cmd)],
        )
