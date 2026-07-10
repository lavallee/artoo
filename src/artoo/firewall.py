"""The deploy firewall: deny-by-default rules for what may leave the repo.

Research material lives next to the presentation; the firewall is what makes
that safe. Only files inside the artifact's site root ship, and even there,
notebook files and ``_``/``.``-prefixed paths are withheld.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .manifest import MANIFEST_NAME, Manifest

# Working-notes filenames that never publish even if placed inside site/.
NOTEBOOK_FILES = {
    "notebook.md",
    "notes.md",
    "priors.md",
    "DECISIONS.md",
    "HANDOFF.md",
    MANIFEST_NAME,
}

# Hidden names that hosts require at the published root.
ALLOWED_HIDDEN = {".nojekyll"}


def is_publishable(rel_path: Path) -> bool:
    """May this site-relative path ship? Deny hidden/underscore segments and notebook files."""
    for part in rel_path.parts:
        if part.startswith(("_", ".")) and part not in ALLOWED_HIDDEN:
            return False
    return rel_path.name not in NOTEBOOK_FILES


def iter_publishable(site_dir: Path):
    """Yield site-relative paths of every file cleared to ship."""
    for path in sorted(site_dir.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(site_dir)
        if is_publishable(rel):
            yield rel


def withheld(site_dir: Path) -> list[Path]:
    """Site-relative paths present in site/ that the firewall refuses to ship."""
    result = []
    for path in sorted(site_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(site_dir)
        if not is_publishable(rel):
            result.append(rel)
    return result


def check(m: Manifest) -> list[str]:
    """Structural firewall problems for an artifact (empty list = clean)."""
    problems = []
    site = m.site_dir
    if not site.is_dir():
        problems.append(f"site root {site} does not exist")
        return problems
    if not (site / "index.html").is_file():
        problems.append(f"site root {site} has no index.html")
    nb = m.notebook_dir
    if nb and nb.exists():
        try:
            nb.resolve().relative_to(site.resolve())
            problems.append("notebook directory sits inside the site root — it would ship")
        except ValueError:
            pass
    return problems


def stage(m: Manifest, dest: Path) -> list[Path]:
    """Copy the publishable site into ``dest``; returns staged relative paths.

    ``dest`` is replaced wholesale — deploy adapters own its lifecycle.
    """
    site = m.site_dir
    if dest.exists():
        shutil.rmtree(dest)
    staged = []
    for rel in iter_publishable(site):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(site / rel, target)
        staged.append(rel)
    return staged
