"""Find artifacts. They can live anywhere in a tree; a repo can hold many."""

from __future__ import annotations

from pathlib import Path

from . import manifest as manifest_mod
from .manifest import MANIFEST_NAME, Manifest

SKIP_DIRS = {
    ".git",
    ".hg",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".artoo",
}


def find_artifacts(root: Path) -> list[Path]:
    """Return artifact directories under ``root`` (inclusive), sorted."""
    root = root.resolve()
    found = []
    if (root / MANIFEST_NAME).is_file():
        found.append(root)
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except (PermissionError, FileNotFoundError):
            continue
        for entry in entries:
            if not entry.is_dir() or entry.is_symlink() or entry.name in SKIP_DIRS:
                continue
            if (entry / MANIFEST_NAME).is_file():
                found.append(entry)
            stack.append(entry)
    return sorted(set(found))


def resolve_artifact(path: Path | None) -> Manifest:
    """Resolve the artifact meant by ``path`` (or the cwd).

    A direct path to an artifact dir or manifest wins; otherwise walk up
    from the given directory looking for one.
    """
    start = (path or Path.cwd()).resolve()
    candidate = start if start.is_dir() else start.parent
    if start.name == MANIFEST_NAME and start.is_file():
        return manifest_mod.load(start)
    for current in [candidate, *candidate.parents]:
        if (current / MANIFEST_NAME).is_file():
            return manifest_mod.load(current)
    nearby = find_artifacts(candidate)
    hint = ""
    if nearby:
        listing = "\n".join(f"  {p}" for p in nearby[:10])
        hint = f"\nArtifacts found under {candidate}:\n{listing}"
    raise FileNotFoundError(
        f"no {MANIFEST_NAME} at or above {start}.{hint}"
    )
