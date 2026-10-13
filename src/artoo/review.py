"""Private, revision-bound review events for any Artoo artifact."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import uuid4

from . import firewall
from .manifest import Manifest


def site_revision(m: Manifest) -> str:
    """Digest exactly the file set Artoo would serve or deploy."""
    digest = hashlib.sha256()
    for relative in firewall.iter_publishable(m.site_dir):
        digest.update(relative.as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256((m.site_dir / relative).read_bytes()).digest())
    return digest.hexdigest()


def _git_state(m: Manifest) -> tuple[str, bool]:
    try:
        head = subprocess.run(
            ["git", "-C", str(m.dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(m.dir), "status", "--porcelain", "--", "."],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return head, bool(dirty)
    except (OSError, subprocess.CalledProcessError):
        return "", False


def _page(m: Manifest, page: str) -> str:
    if not page:
        return ""
    value = PurePosixPath(page.lstrip("/"))
    if value.is_absolute() or ".." in value.parts or not value.parts:
        raise ValueError("--page must be a site-relative path without '..'")
    candidate = m.site_dir.joinpath(*value.parts)
    if candidate.is_dir():
        candidate /= "index.html"
    try:
        candidate.resolve().relative_to(m.site_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"--page escapes the site root: {page}") from exc
    if (not candidate.is_file() or candidate.is_symlink()
            or not firewall.is_publishable(candidate.relative_to(m.site_dir))):
        raise ValueError(f"--page does not name a served file: {page}")
    return candidate.relative_to(m.site_dir).as_posix()


def record(m: Manifest, text: str, *, page: str = "", resolves: str = "") -> dict:
    """Append a finding or resolution under work/, never in the served site."""
    if not text.strip():
        raise ValueError("review text cannot be empty")
    target = _page(m, page)
    path = m.dir / "work" / "reviews.jsonl"
    if resolves:
        prior = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        findings = {item["id"] for item in prior if item.get("event") == "finding"}
        closed = {item["resolves"] for item in prior if item.get("event") == "resolution"}
        if resolves not in findings or resolves in closed:
            raise ValueError(f"--resolves must name an open finding id: {resolves}")
    head, dirty = _git_state(m)
    event = {
        "schema": "artoo-review/1",
        "id": uuid4().hex,
        "event": "resolution" if resolves else "finding",
        "artifact": m.slug,
        "site_revision": site_revision(m),
        "git_head": head,
        "git_dirty": dirty,
        "page": target,
        "text": text.strip(),
        "resolves": resolves,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.parent.mkdir(exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event
