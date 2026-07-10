"""Site libraries: vendored with provenance.

The tension a site library resolves: artifacts must be self-contained and
stable (they keep rendering when the tooling moves on) yet easy to upgrade.
So libraries are *copied into* the artifact's site (``site/lib/<name>/``)
and the manifest records name, version, and a content hash. From the hash,
``status`` can tell intact / locally modified / outdated apart, and
``update`` re-vendors deliberately.

Libraries resolve from the ``artoo.libraries`` entry-point group; external
libraries live in their own repos/packages. artoo ships one built-in,
``artoo-kit``. One-off assets (a JS runtime like mermaid) are vendored from
a URL and recorded under ``[[vendor]]`` with a pinned hash.
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path

from ..manifest import Manifest

LIB_ROOT = "lib"  # under the site dir


@dataclass
class Library:
    name: str
    version: str
    root: Path  # directory whose files get vendored

    def files(self) -> list[Path]:
        return sorted(p for p in self.root.rglob("*") if p.is_file())


def _builtin() -> dict[str, Library]:
    from .kit import library as kit

    return {kit.name: kit}


def available() -> dict[str, Library]:
    registry = _builtin()
    for ep in entry_points(group="artoo.libraries"):
        if ep.name in registry:
            continue
        try:
            lib = ep.load()
        except Exception:
            continue
        if isinstance(lib, Library):
            registry[ep.name] = lib
    return registry


def get(name: str) -> Library:
    registry = available()
    if name not in registry:
        known = ", ".join(sorted(registry))
        raise KeyError(f"no site library named {name!r} (available: {known})")
    return registry[name]


def tree_hash(root: Path) -> str:
    """Deterministic content hash of a directory: sha256 over (relpath, bytes)."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def vendored_dir(m: Manifest, name: str) -> Path:
    return m.site_dir / LIB_ROOT / name


def add(m: Manifest, name: str) -> dict:
    """Vendor a library into the site and record provenance in the manifest."""
    lib = get(name)
    dest = vendored_dir(m, name)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(lib.root, dest)
    record = {"name": lib.name, "version": lib.version, "sha256": tree_hash(dest)}
    m.libraries = [entry for entry in m.libraries if entry.get("name") != name]
    m.libraries.append(record)
    m.save()
    return record


def status(m: Manifest) -> list[dict]:
    """One row per recorded library: intact / modified / missing / outdated."""
    rows = []
    for entry in m.libraries:
        name = entry.get("name", "?")
        row = {"name": name, "version": entry.get("version", "?"), "state": "intact"}
        dest = vendored_dir(m, name)
        if not dest.is_dir():
            row["state"] = "missing"
        elif tree_hash(dest) != entry.get("sha256"):
            row["state"] = "modified"
        else:
            try:
                current = get(name)
                if current.version != entry.get("version"):
                    row["state"] = f"outdated (→ {current.version})"
            except KeyError:
                pass  # external lib not installed here; vendored copy still works
        rows.append(row)
    return rows


def update(m: Manifest, name: str) -> dict:
    """Re-vendor from the currently available library version."""
    if not any(entry.get("name") == name for entry in m.libraries):
        raise KeyError(f"{name!r} is not recorded in this artifact's manifest")
    return add(m, name)


def vendor_url(m: Manifest, name: str, url: str, *, rel_path: str = "") -> dict:
    """Vendor a single asset from a URL with a pinned hash (e.g. mermaid)."""
    rel = rel_path or f"{m.site}/{LIB_ROOT}/vendor/{url.rsplit('/', 1)[-1]}"
    dest = m.dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 - explicit user action
        data = resp.read()
    dest.write_bytes(data)
    record = {
        "name": name,
        "url": url,
        "sha256": hashlib.sha256(data).hexdigest(),
        "path": rel,
    }
    m.vendor = [entry for entry in m.vendor if entry.get("name") != name]
    m.vendor.append(record)
    m.save()
    return record
