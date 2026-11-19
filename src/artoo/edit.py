"""Open an artifact in an in-page editor: ``artoo edit``.

Artoo does not edit pages itself. It hands the built site, its source map and
the artifact's edit settings to Copycat, an editor that serves the page with
editing on it and writes changes back to the Markdown sources. Copycat is a
soft dependency like flip: it is found through ``--copycat`` or
``COPYCAT_HOME``, and nothing here runs without it.

The editor's configuration is the artifact's own ``[edit] config`` when the
manifest names one (registered files are the editor's write boundary, so an
artifact with generated figure text or a masthead in TOML keeps an explicit
file). Otherwise one is generated into ``work/editor/copycat.json`` from the
source map: every Markdown file the pages were rendered from, the manifest
title, comments and section status where ``[edit]`` puts them, and
``artoo build --no-browser .`` as the rebuild that runs after each save.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from . import sourcemap
from .manifest import Manifest

GENERATED = Path("work") / "editor" / "copycat.json"


class EditError(Exception):
    """A road sign: what is missing and the flag, key or command that fixes it."""


def copycat_home(explicit: Path | None = None) -> Path:
    candidate = explicit or (Path(os.environ["COPYCAT_HOME"]) if os.environ.get("COPYCAT_HOME") else None)
    if candidate is None:
        raise EditError(
            "artoo edit needs Copycat: pass --copycat DIR or set COPYCAT_HOME to its checkout"
        )
    if not (candidate / "src" / "server.js").is_file():
        raise EditError(f"{candidate} is not a Copycat checkout (no src/server.js); fix --copycat or COPYCAT_HOME")
    return candidate.resolve()


def check_origin(origin: str) -> str:
    share = urlsplit(origin)
    if share.scheme != "https" or not share.netloc or origin != f"https://{share.netloc}" or share.username:
        raise EditError(f"--share-origin must be an exact https:// origin such as https://host.example, not {origin!r}")
    return origin


def generated_config(m: Manifest, port: int) -> dict:
    """A Copycat configuration derived from the source map and [edit]."""
    data = sourcemap.read(m.dir)
    if data is None:
        raise EditError(
            "no source map: set `sourcemap = true` under [content] in artifact.toml, then `artoo build`"
        )
    markdown_files = sorted(
        {
            block["file"]
            for page in data["pages"].values()
            for block in page["blocks"]
            if block["file"].endswith(".md") and not block["file"].startswith("..")
        }
    )
    sources: list[dict] = [
        {
            "file": "artifact.toml",
            "toml": ["artifact.title"],
            "scope": ".site-nav .brand, .article-masthead",
            "label": "Title",
        }
    ]
    for name in markdown_files:
        sources.append(
            {
                "file": name,
                "markdown": True,
                "title": True,
                "frontmatter": ["description"],
                "scope": "main.article",
                "sourceView": True,
                "status": bool(m.edit_status),
            }
        )
    path = f"/{m.slug}/"
    page: dict = {
        "name": m.title,
        "url": f"http://127.0.0.1:{port}{path}index.html",
        "selector": "main.article",
        "serve": {"dir": m.site, "path": path},
        "conflicts": "file",
        "sourcemap": str(sourcemap.MAP_FILE),
        "sources": sources,
        "build": {"command": ["artoo", "build", "--no-browser", "."], "timeout": 300},
    }
    if m.edit_comments:
        page["comments"] = m.edit_comments
    if m.edit_status:
        page["status"] = {"file": m.edit_status}
    # Paths in a Copycat config are relative to the config file.
    return {"root": "../..", "state": "copycat", "pages": [page]}


def config_path(m: Manifest, port: int) -> Path:
    if m.edit_config:
        path = m.dir / m.edit_config
        if not path.is_file():
            raise EditError(f"[edit] config names {m.edit_config}, which does not exist")
        return path
    config = generated_config(m, port)
    path = m.dir / GENERATED
    path.parent.mkdir(parents=True, exist_ok=True)
    for name in (m.edit_comments, m.edit_status):
        if name:
            (m.dir / name).parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def command(
    m: Manifest,
    *,
    copycat: Path,
    port: int,
    share_origin: str = "",
    agent: str = "none",
    agent_bin: str = "",
) -> tuple[list[str], dict[str, str]]:
    """The editor's command line and environment; ``launch`` runs it."""
    node = shutil.which("node")
    if not node:
        raise EditError("artoo edit needs Node.js 22 or later on PATH for Copycat")
    env = {
        **os.environ,
        "COPYCAT_CONFIG": str(config_path(m, port)),
        "PORT": str(port),
        "HOST": "127.0.0.1",
        "COPYCAT_AGENT_PRESET": agent,
    }
    if share_origin:
        env["COPYCAT_HOST_ORIGINS"] = check_origin(share_origin)
    if agent != "none":
        if not agent_bin or not Path(agent_bin).is_absolute():
            raise EditError(f"--agent {agent} needs --agent-bin with the absolute path of its CLI")
        env["COPYCAT_AGENT_BIN"] = agent_bin
    return [node, str(copycat / "src" / "server.js")], env


def launch(argv: list[str], env: dict[str, str]) -> None:  # pragma: no cover - replaces the process
    os.execve(argv[0], argv, env)
