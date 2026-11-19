"""Source maps: which source file and lines each rendered block came from.

With ``[content] sourcemap = true`` a build marks every block it renders from
Markdown (heading, paragraph, list item, table, quote, figure, and the page's
title, dek and masthead) with an opaque ``data-artoo-src`` id, and writes
``work/artoo-sourcemap.json`` (contract ``artoo-sourcemap/1``) naming, for each
page and id, the file and 1-based line range the block came from, plus the
SHA-256 of every file at build time. An in-page editor reads the map instead of
matching rendered text back to Markdown; a file whose hash no longer matches
has changed since the build, so the editor knows that part of the map is stale.

The ids carry no paths, so the published HTML reveals nothing about the source
tree; the map itself stays in ``work/``, which never ships.

A build command that assembles the Markdown Artoo renders from other files
keeps the map true with origin comments, one per line:

    <!-- artoo:source book/modules/03-timing.md:1 -->
    <!-- artoo:source book/specs/03-curve.json derives=work/receipt.json -->
    <!-- artoo:source - -->

The first says the following lines are that file from line 1 on; the second
that the next block was generated from a file with no line mapping, and was
derived from the listed files (comma-separated); ``-`` marks generated lines
with no source. The comments never render. Without any, a page's blocks map
to the page's own Markdown file.

When the artifact attaches a notebook with ``[research] publish = false``, the
map also carries each block's evidence: the notebook sources whose captured
SHA-256 equals a file the block came from or derives from, the claims citing
those sources whose numbers appear in the block, and the derived files the
notebook has not captured. Ids a page declares in front matter
(``evidence: Q20, C30``) are checked against the notebook.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CONTRACT = "artoo-sourcemap/1"
MAP_FILE = Path("work") / "artoo-sourcemap.json"
ATTR = "data-artoo-src"
_ORIGIN = re.compile(r"^<!--\s*artoo:source\s+(\S+?)(?::(\d+))?((?:\s+derives=\S+)?)\s*-->$")
_TAGS = re.compile(r"<[^>]+>")
_MARKED = re.compile(r'<([a-z][a-z0-9]*)\b[^>]*\bdata-artoo-src="(a\d+)"[^>]*>(.*?)</\1>', re.S)


@dataclass(frozen=True)
class Origin:
    file: str  # artifact-relative; "-" for generated lines
    line: int | None
    derives: tuple[str, ...] = ()


def split(source: str, page_file: str) -> tuple[str, list[Origin]]:
    """Strip origin comments; return the clean source and an origin per clean line.

    A comment inside the text becomes a blank line, so it always ends the block
    before it and line numbers in error messages stay close to the page file.
    Leading comments are removed entirely so front matter still opens the page.
    """
    lines = source.split("\n")
    out: list[str] = []
    origins: list[Origin] = []
    current: tuple[str, int | None, tuple[str, ...], int] | None = None
    for number, line in enumerate(lines, start=1):
        match = _ORIGIN.match(line.strip())
        if match:
            derives = tuple(
                part for part in match.group(3).strip().removeprefix("derives=").split(",") if part
            )
            if out:
                out.append("")
                origins.append(Origin("-", None))
            current = (match.group(1), int(match.group(2)) if match.group(2) else None, derives, len(out))
            continue
        out.append(line)
        if current is None:
            origins.append(Origin(page_file, number))
        else:
            file, first, derives, start = current
            offset = len(out) - 1 - start
            origins.append(Origin(file, first + offset if first is not None else None, derives))
    return "\n".join(out), origins


def has_origins(source: str) -> bool:
    return any(_ORIGIN.match(line.strip()) for line in source.split("\n"))


@dataclass
class PageMap:
    """Collects blocks for one page while it renders."""

    page: str
    origins: list[Origin]
    blocks: list[dict] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)  # block id → plain text, for evidence
    count: int = 0

    def _entry(self, kind: str, start: int, end: int) -> dict | None:
        span = [self.origins[i] for i in range(start, min(end, len(self.origins) - 1) + 1)]
        span = [o for o in span if o.file != "-"]
        if not span:
            return None
        first = span[0]
        last = [o for o in span if o.file == first.file][-1]
        entry: dict = {"kind": kind, "file": first.file}
        entry["lines"] = [first.line, last.line] if first.line is not None else None
        if first.derives:
            entry["derives"] = list(first.derives)
        return entry

    def mark(self, kind: str, start: int, end: int) -> str:
        """An attribute for the block on clean lines ``start``..``end`` (0-based)."""
        entry = self._entry(kind, start, end)
        if entry is None:
            return ""
        self.count += 1
        entry = {"id": f"a{self.count}", **entry}
        self.blocks.append(entry)
        return f' {ATTR}="{entry["id"]}"'

    def record(self, kind: str, start: int, end: int, rendered: str = "") -> None:
        """A block that cannot carry an attribute (raw HTML from a ``:::`` block)."""
        entry = self._entry(kind, start, end)
        if entry is None:
            return
        entry = {"id": None, **entry}
        self.blocks.append(entry)
        if rendered:
            self.texts[f"#{len(self.blocks) - 1}"] = plain(rendered)

    def special(self, kind: str, file: str, lines: list[int] | None = None, key: str = "") -> str:
        """A page element outside the Markdown body: title, dek, masthead."""
        self.count += 1
        entry: dict = {"id": f"a{self.count}", "kind": kind, "file": file, "lines": lines}
        if key:
            entry["key"] = key
        self.blocks.append(entry)
        return f' {ATTR}="{entry["id"]}"'

    def origin_of(self, index: int) -> Origin | None:
        return self.origins[index] if 0 <= index < len(self.origins) else None

    def collect_texts(self, page_html: str) -> None:
        for match in _MARKED.finditer(page_html):
            self.texts[match.group(2)] = plain(match.group(3))


def plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(_TAGS.sub(" ", fragment))).strip()


def line_of(source: str, offset: int) -> int:
    """0-based line index of a character offset."""
    return source.count("\n", 0, offset)


# -- the map file ---------------------------------------------------------------


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def write(artifact_dir: Path, pages: dict[str, PageMap], *, generator: str,
          declared: dict[str, list[str]] | None = None,
          projection: dict | None = None,
          projection_file: str = "") -> tuple[Path, list[str], list[str]]:
    """Write work/artoo-sourcemap.json. Returns (path, notes, problems)."""
    files: dict[str, str | None] = {}
    for page in pages.values():
        for block in page.blocks:
            for name in [block["file"], *block.get("derives", [])]:
                if name not in files:
                    files[name] = _sha(artifact_dir / name)
    notes: list[str] = []
    problems: list[str] = []
    out_pages: dict[str, dict] = {}
    evidence_index = _EvidenceIndex(projection) if projection else None
    for name, page in pages.items():
        entry: dict = {"source": page.page, "blocks": []}
        for index, block in enumerate(page.blocks):
            block = dict(block)
            if evidence_index:
                text = page.texts.get(block["id"] or f"#{index}", "")
                block_evidence = evidence_index.resolve(
                    [block["file"], *block.get("derives", [])], files, text
                )
                if block_evidence:
                    block["evidence"] = block_evidence
            entry["blocks"].append(block)
        refs = (declared or {}).get(name, [])
        if refs:
            known = evidence_index.ids if evidence_index else set()
            unknown = [ref for ref in refs if ref not in known]
            if evidence_index and unknown:
                problems.append(
                    f"{page.page}: evidence names {', '.join(unknown)}, which the attached "
                    "notebook does not have; fix the front-matter `evidence:` line"
                )
            entry["evidence"] = [ref for ref in refs if ref in known] if evidence_index else refs
        out_pages[name] = entry
    data = {
        "contract": CONTRACT,
        "generator": generator,
        "attribute": ATTR,
        "files": {name: digest for name, digest in sorted(files.items())},
        "pages": out_pages,
    }
    if evidence_index:
        uncaptured = sorted(
            {name for page in out_pages.values() for block in page["blocks"]
             for name in block.get("evidence", {}).get("uncaptured", [])}
        )
        linked = sum(
            1 for page in out_pages.values() for block in page["blocks"]
            if block.get("evidence", {}).get("claims")
        )
        claims = {
            claim for page in out_pages.values() for block in page["blocks"]
            for claim in block.get("evidence", {}).get("claims", [])
        }
        data["evidence"] = {
            "notebook": (projection or {}).get("notebook", {}).get("uid", ""),
            "projection": projection_file,
            "uncaptured": uncaptured,
        }
        notes.append(
            f"evidence: {linked} block(s) on {len(out_pages)} page(s) carry {len(claims)} notebook "
            f"claim(s); {len(uncaptured)} derived file(s) are not in the notebook at their current revision"
        )
    path = artifact_dir / MAP_FILE
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path, notes, problems


def read(artifact_dir: Path) -> dict | None:
    try:
        data = json.loads((artifact_dir / MAP_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if data.get("contract") == CONTRACT else None


# -- evidence -------------------------------------------------------------------

_NUMBER = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(%?)(?![\w])")


def numbers(text: str) -> set[str]:
    """The distinctive numbers in a claim, as a page would print them.

    Years and small counts are too common to tie a claim to a block, so only a
    percentage, a number with a thousands separator, or one of three or more
    digits that is not a year counts. A decimal percentage also matches its
    rounded form ("66.1%" → "66%")."""
    found: set[str] = set()
    for value, percent in _NUMBER.findall(text):
        digits = value.replace(",", "")
        if percent:
            found.add(value + "%")
            if "." in value:
                found.add(f"{round(float(value))}%")
        elif "," in value:
            found.add(value)
        elif "." not in value and len(digits) >= 3 and not (len(digits) == 4 and 1900 <= int(digits) <= 2099):
            found.add(value)
            if len(digits) >= 4:
                found.add(f"{int(digits):,}")
    return found


class _EvidenceIndex:
    def __init__(self, projection: dict):
        self.by_hash: dict[str, str] = {}
        for source in projection.get("sources", []) or []:
            digest = source.get("sha256")
            if isinstance(digest, str) and digest and isinstance(source.get("id"), str):
                self.by_hash.setdefault(digest, source["id"])
        self.claims = [c for c in projection.get("claims", []) or [] if isinstance(c, dict)]
        self.claim_numbers = {c.get("id"): numbers(str(c.get("text", ""))) for c in self.claims}
        self.ids = {
            item.get("id")
            for key in ("sources", "claims", "questions", "decisions")
            for item in projection.get(key, []) or []
            if isinstance(item, dict)
        }

    def resolve(self, names: list[str], digests: dict[str, str | None], text: str) -> dict:
        sources: list[str] = []
        uncaptured: list[str] = []
        for index, name in enumerate(names):
            digest = digests.get(name)
            source = self.by_hash.get(digest or "")
            if source and source not in sources:
                sources.append(source)
            elif not source and index:  # only derived inputs are expected to be captured
                uncaptured.append(name)
        claims = []
        if sources and text:
            padded = f" {text} "
            for claim in self.claims:
                if not set(claim.get("sources", []) or []) & set(sources):
                    continue
                wanted = self.claim_numbers.get(claim.get("id")) or set()
                if any(re.search(rf"(?<![\w.,]){re.escape(n)}(?![\w])", padded) for n in wanted):
                    claims.append(claim["id"])
        out: dict = {}
        if sources:
            out["sources"] = sources
        if claims:
            out["claims"] = claims
        if uncaptured:
            out["uncaptured"] = uncaptured
        return out
