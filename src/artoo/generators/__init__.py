"""Generators: plugins that produce or update artifacts.

A generator is a ``click.Command`` exposed through the ``artoo.generators``
entry-point group, so ``artoo generate <name> --help`` is self-documenting
and third-party generators ship as ordinary packages. The built-ins are
registered directly so a source checkout works uninstalled.
"""

from __future__ import annotations

from importlib.metadata import entry_points

import click


def _builtin() -> dict[str, click.Command]:
    from .explainer import generate as explainer

    return {"explainer": explainer}


def available() -> dict[str, click.Command]:
    registry = _builtin()
    for ep in entry_points(group="artoo.generators"):
        if ep.name in registry:
            continue
        try:
            command = ep.load()
        except Exception:
            continue
        if isinstance(command, click.Command):
            registry[ep.name] = command
    return registry
