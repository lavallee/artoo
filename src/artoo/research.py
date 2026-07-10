"""Research backing: record what a generator learned, with provenance.

When flip (``artoo[research]``) is installed and the artifact has a
notebook, generator runs are recorded as reporter's-notebook sources,
claims, and sessions. Without flip, the same calls append to a plain
markdown log in ``work/``. Either way the material stays behind the
deploy firewall.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .manifest import Manifest


def _flip():
    try:
        import flip.claims
        import flip.manifest
        import flip.sessions
        import flip.sources
        import flip.views

        return flip
    except Exception:
        return None


class ResearchLog:
    """One generator run's research trail. Context-manage it around a run."""

    def __init__(self, m: Manifest, *, tool: str):
        self.manifest = m
        self.tool = tool
        self._flip = _flip()
        self._nb_root: Path | None = None
        self._session: Path | None = None
        self._fallback: Path | None = None
        self._dirty = False

        nb = m.notebook_dir
        if self._flip and nb and (nb / "index.md").is_file():
            self._nb_root = nb
        else:
            work = m.dir / "work"
            work.mkdir(exist_ok=True)
            self._fallback = work / "research-log.md"

    def __enter__(self):
        if self._nb_root:
            try:
                self._session = self._flip.sessions.start_session(
                    self._nb_root, self.tool, tools=[self.tool]
                )
            except Exception:
                self._nb_root = None  # degrade to fallback for the whole run
                self._fallback = self.manifest.dir / "work" / "research-log.md"
        if self._fallback:
            stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._append(f"\n## {self.tool} run — {stamp}\n")
        return self

    def __exit__(self, *exc):
        if self._nb_root and self._session:
            try:
                self._flip.sessions.end_session(self._nb_root, self._session)
                self._tail()
            except Exception:
                pass
        return False

    def _append(self, text: str) -> None:
        assert self._fallback is not None
        self._fallback.parent.mkdir(exist_ok=True)
        with self._fallback.open("a", encoding="utf-8") as f:
            f.write(text + "\n")

    def _tail(self) -> None:
        """flip mutation tail: touch + regenerate views, once per batch."""
        if not self._nb_root:
            return
        try:
            self._flip.manifest.touch_updated(self._nb_root)
            self._flip.views.regenerate(self._nb_root)
        except Exception:
            pass

    def add_source(self, target: str, note: str = "") -> None:
        if self._nb_root:
            try:
                self._flip.sources.add_source(self._nb_root, target, note=note)
                self._dirty = True
                return
            except Exception:
                pass
        self._append(f"- source: `{target}` — {note}")

    def add_claim(self, text: str, *, sources: list[str] | None = None,
                  load_bearing: bool = False) -> None:
        if self._nb_root:
            try:
                self._flip.claims.add_claim(
                    self._nb_root, text,
                    sources=sources or [], load_bearing=load_bearing,
                )
                self._dirty = True
                return
            except Exception:
                pass
        marker = " [load-bearing]" if load_bearing else ""
        refs = f" ({', '.join(sources)})" if sources else ""
        self._append(f"- claim{marker}: {text}{refs}")

    def note(self, text: str) -> None:
        if self._fallback:
            self._append(f"- {text}")
