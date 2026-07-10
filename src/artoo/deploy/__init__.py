"""Deploy adapters: registry and dispatch.

Adapters are discovered from the ``artoo.deployers`` entry-point group so
they can ship as separate packages; the built-ins are registered directly
so artoo works uninstalled (from a source checkout).
"""

from __future__ import annotations

from importlib.metadata import entry_points

from .base import DeployContext, Deployer, DeployResult


def _builtin() -> dict[str, type[Deployer]]:
    from .command import CommandDeployer
    from .github_pages import GitHubPagesDeployer
    from .rsync import RsyncDeployer

    return {
        GitHubPagesDeployer.name: GitHubPagesDeployer,
        RsyncDeployer.name: RsyncDeployer,
        CommandDeployer.name: CommandDeployer,
    }


def available() -> dict[str, type[Deployer]]:
    registry = _builtin()
    for ep in entry_points(group="artoo.deployers"):
        if ep.name not in registry:
            try:
                registry[ep.name] = ep.load()
            except Exception:  # a broken third-party plugin must not break artoo
                continue
    return registry


def get(name: str) -> type[Deployer]:
    registry = available()
    if name not in registry:
        known = ", ".join(sorted(registry))
        raise KeyError(f"no deploy adapter named {name!r} (available: {known})")
    return registry[name]


__all__ = ["DeployContext", "Deployer", "DeployResult", "available", "get"]
