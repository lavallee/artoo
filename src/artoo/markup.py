"""Read the class vocabulary out of CSS, then check markup against it.

Two jobs, one parser. A site library is vendored as bytes, so the vocabulary
an artifact can actually use is whatever its own ``site/lib/<name>/*.css``
defines — not whatever the library shipped at some other version. That makes
the vendored CSS the only honest source of truth for both halves here:

``base_classes`` extracts the *public* vocabulary (BEM elements and modifiers
folded back onto their parent) so a library's documented class list can be
tested against the stylesheet it documents. ``check`` compares an artifact's
hand-authored markup against the full vocabulary and reports classes invented
inside a library's own namespace.

The namespace test is what keeps this precise. An author's ``.chart-bar`` is
their business and passes silently; an ``.article-wide`` is a guess at a kit
class that does not exist, and it will render as nothing at all. Flagging the
second without nagging about the first is the whole design.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_RULE = re.compile(r"([^{}]*)\{")
_LEADING_CLASS = re.compile(r"^\.(-?[A-Za-z_][\w-]*)")
_ANY_CLASS = re.compile(r"\.(-?[A-Za-z_][\w-]*)")
_CLASS_ATTR = re.compile(r"""\bclass\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)


def _selector_lists(css: str):
    """Yield each selector list in ``css`` — the text preceding every ``{``.

    Deliberately not a real CSS parser: declarations never contain braces, so
    taking the text after the last ``}`` before each ``{`` lands on selectors
    and nothing else. At-rules are skipped; the rules nested inside them are
    picked up by the next match.
    """
    css = _COMMENT.sub("", css)
    for match in _RULE.finditer(css):
        chunk = match.group(1).rsplit("}", 1)[-1].strip()
        if chunk and not chunk.startswith("@"):
            yield chunk


def fold(name: str) -> str:
    """Fold a BEM element or modifier back onto the class that owns it.

    ``article-masthead__name`` and ``callout--warn`` are not vocabulary of
    their own; they are part of the contract of ``article-masthead`` and
    ``callout``. Documenting them separately would be noise.
    """
    for separator in ("__", "--"):
        if separator in name:
            name = name.split(separator, 1)[0]
    return name


def base_classes(css: str) -> set[str]:
    """Public classes a stylesheet defines: the leading class of each rule, folded."""
    found = set()
    for chunk in _selector_lists(css):
        for selector in chunk.split(","):
            match = _LEADING_CLASS.match(selector.strip())
            if match:
                found.add(fold(match.group(1)))
    return found


def declared_classes(css: str) -> set[str]:
    """Every class the stylesheet mentions anywhere in a selector.

    Broader than ``base_classes`` on purpose: markup writes
    ``class="callout callout--warn"`` and ``<span class="value">``, and all
    three are legitimate even though only ``callout`` is a public entry point.
    """
    return {
        match.group(1)
        for chunk in _selector_lists(css)
        for match in _ANY_CLASS.finditer(chunk)
    }


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def base_classes_in_dir(directory: Path) -> set[str]:
    """Union of ``base_classes`` over every stylesheet in a directory."""
    found: set[str] = set()
    for path in sorted(directory.rglob("*.css")):
        found |= base_classes(_read(path))
    return found


def declared_classes_in_dir(directory: Path) -> set[str]:
    """Union of ``declared_classes`` over every stylesheet in a directory."""
    found: set[str] = set()
    for path in sorted(directory.rglob("*.css")):
        found |= declared_classes(_read(path))
    return found


def classes_used(html: str) -> set[str]:
    """Every class token appearing in a ``class=`` attribute."""
    used = set()
    for match in _CLASS_ATTR.finditer(html):
        used.update((match.group(1) or match.group(2) or "").split())
    return used


@dataclass(frozen=True)
class Finding:
    """One class used in markup that its library's namespace does not define."""

    file: str
    cls: str
    library: str
    namespace: str
    suggestion: str = ""

    def message(self) -> str:
        hint = f' (did you mean "{self.suggestion}"?)' if self.suggestion else ""
        return (
            f'{self.file}: class "{self.cls}" is in the {self.library} '
            f"`{self.namespace}` namespace, but the vendored stylesheet defines "
            f"no such class{hint} — `artoo docs {self.library}` lists the "
            f"vocabulary it does define"
        )


def closest(cls: str, known: set[str], namespace: str = "") -> str:
    """The nearest real class to a mistaken one, or ``""`` if nothing is close.

    An error that only says "no" costs the reader another round trip, and most
    mistyped classes are a near miss on a real one. But a *confident wrong*
    suggestion is worse than none, and comparing whole names produces them
    freely: every class in a namespace shares its prefix, so the prefix
    dominates the similarity score and any unknown ``article-*`` looks like a
    near miss on whichever ``article-*`` is closest in length.

    So inside a namespace the comparison runs on what follows it. ``wide`` is
    not close to ``dek`` and gets no suggestion — correctly, because
    ``article-wide`` is an invention rather than a typo — while ``ful`` is
    close to ``full`` and gets one.
    """
    if namespace:
        candidates = {c[len(namespace):]: c for c in known if c.startswith(namespace)}
        matches = difflib.get_close_matches(
            cls[len(namespace):], sorted(candidates), n=1, cutoff=0.7
        )
        return candidates[matches[0]] if matches else ""
    matches = difflib.get_close_matches(cls, sorted(known), n=1, cutoff=0.7)
    return matches[0] if matches else ""
