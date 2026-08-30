"""Deterministic Markdown rendering for article and collection forms."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .generators.notebook_report import markdown
from .manifest import Manifest

_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_HEADING = re.compile(r"<(h[23])>(.*?)</\1>")
_TAGS = re.compile(r"<[^>]+>")
_OUTPUTS = "artoo-content.json"


@dataclass
class RenderResult:
    status: str
    written: list[Path] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _title(source: str, fallback: str) -> str:
    match = _H1.search(source)
    return match.group(1).strip() if match else fallback


def _without_first_h1(source: str) -> str:
    return _H1.sub("", source, count=1).lstrip()


def _slug(value: str, used: set[str]) -> str:
    plain = html.unescape(_TAGS.sub("", value)).lower()
    base = re.sub(r"[^a-z0-9]+", "-", plain).strip("-") or "section"
    candidate = base
    number = 2
    while candidate in used:
        candidate = f"{base}-{number}"
        number += 1
    used.add(candidate)
    return candidate


def _body_and_toc(source: str) -> tuple[str, list[tuple[int, str, str]]]:
    fragment = markdown.to_html(_without_first_h1(source))
    used: set[str] = set()
    toc: list[tuple[int, str, str]] = []

    def add_id(match: re.Match) -> str:
        tag = match.group(1)
        text = match.group(2)
        anchor = _slug(text, used)
        toc.append((int(tag[1]), _TAGS.sub("", text), anchor))
        return f'<{tag} id="{anchor}">{text}</{tag}>'

    return _HEADING.sub(add_id, fragment), toc


def _toc(items: list[tuple[int, str, str]]) -> str:
    if not items:
        return ""
    links = "\n".join(
        f'      <li><a href="#{anchor}">{html.escape(label)}</a></li>'
        for _level, label, anchor in items
    )
    return f'  <nav class="toc" aria-label="On this page"><ol>\n{links}\n  </ol></nav>'


def _evidence(m: Manifest) -> tuple[str, str]:
    if not (m.site_dir / "data" / "provenance.js").is_file():
        return "", ""
    panel = '  <section class="provenance article-breakout" data-artoo-provenance></section>'
    scripts = (
        '<script src="data/provenance.js"></script>\n'
        '<script src="lib/artoo-kit/provenance.js"></script>'
    )
    return panel, scripts


def _record_outputs(m: Manifest, written: list[Path]) -> None:
    """Prune only outputs a prior Artoo render explicitly claimed."""
    registry = m.dir / "work" / _OUTPUTS
    prior = []
    if registry.is_file():
        try:
            recorded = json.loads(registry.read_text(encoding="utf-8"))
            if recorded.get("contract") == "artoo-content/1":
                files = recorded.get("files", [])
                prior = files if isinstance(files, list) else []
        except (OSError, json.JSONDecodeError, AttributeError):
            prior = []
    current = {str(path.relative_to(m.dir)) for path in written}
    site = m.site_dir.resolve()
    for name in prior:
        path = (m.dir / str(name)).resolve()
        try:
            path.relative_to(site)
        except ValueError:
            continue
        if str(path.relative_to(m.dir)) not in current and path.suffix == ".html":
            path.unlink(missing_ok=True)
    registry.parent.mkdir(exist_ok=True)
    registry.write_text(
        json.dumps({"contract": "artoo-content/1", "files": sorted(current)}, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _head(m: Manifest, title: str) -> str:
    description = html.escape(m.description or f"{title} — {m.kind}", quote=True)
    return f"""<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{description}">
<link rel="icon" href="lib/artoo-kit/favicon.svg">
<link rel="stylesheet" href="lib/artoo-kit/tokens.css">
<link rel="stylesheet" href="lib/artoo-kit/base.css">
<link rel="stylesheet" href="lib/artoo-kit/article.css">
<link rel="stylesheet" href="lib/artoo-kit/components.css">
</head>"""


def _dates(m: Manifest) -> str:
    published = f'Published <time datetime="{m.created}">{m.created}</time>'
    if not m.updated or m.updated == m.created:
        return published
    return published + f' · Updated <time datetime="{m.updated}">{m.updated}</time>'


def _article(m: Manifest, source: str) -> str:
    title = _title(source, m.title)
    body, toc = _body_and_toc(source)
    evidence, scripts = _evidence(m)
    return f"""<!doctype html>
<html lang="en" data-theme="light">
{_head(m, title)}
<body>
<header class="article-masthead">
  <a class="article-masthead__name" href="index.html">{html.escape(m.title)}</a>
  <span class="article-masthead__label">Artoo artifact</span>
</header>
<main class="article" data-claim-anchors>
  <header class="article-header">
    <div class="article-kicker">{html.escape(m.kind)}</div>
    <h1 class="article-title">{html.escape(title)}</h1>
    <p class="article-dek">{html.escape(m.description)}</p>
    <p class="article-byline">{_dates(m)}</p>
  </header>
{_toc(toc)}
{body}
{evidence}
  <footer class="article-colophon">
    Built as a self-contained artifact with
    <a href="https://github.com/lavallee/artoo">Artoo</a>.
  </footer>
</main>
{scripts}
</body>
</html>
"""


def _collection_page(
    m: Manifest,
    source: str,
    pages: list[tuple[str, str]],
    position: int,
) -> str:
    slug, fallback = pages[position]
    title = _title(source, fallback)
    body, toc = _body_and_toc(source)
    evidence, scripts = _evidence(m)
    nav = "\n".join(
        "  <a{} href=\"{}\">{}</a>".format(
            ' aria-current="page"' if index == position else "",
            "index.html" if page_slug == "index" else f"{page_slug}.html",
            html.escape(page_title),
        )
        for index, (page_slug, page_title) in enumerate(pages)
    )
    previous = pages[position - 1] if position else None
    following = pages[position + 1] if position + 1 < len(pages) else None
    pager = []
    if previous:
        href = "index.html" if previous[0] == "index" else f"{previous[0]}.html"
        pager.append(f'<a rel="prev" href="{href}">← {html.escape(previous[1])}</a>')
    if following:
        href = "index.html" if following[0] == "index" else f"{following[0]}.html"
        pager.append(f'<a rel="next" href="{href}">{html.escape(following[1])} →</a>')
    return f"""<!doctype html>
<html lang="en" data-theme="light">
{_head(m, title)}
<body>
<nav class="site-nav" aria-label="Collection">
  <a class="brand" href="index.html">{html.escape(m.title)}</a>
  <button class="nav-toggle" type="button" aria-label="Menu" aria-expanded="false">Menu</button>
  <div class="nav-links">
{nav}
  </div>
</nav>
<main class="article" data-claim-anchors>
  <nav aria-label="Breadcrumb"><a href="index.html">{html.escape(m.title)}</a> / {html.escape(title)}</nav>
  <header class="article-header">
    <div class="article-kicker">{html.escape(m.kind)}</div>
    <h1 class="article-title">{html.escape(title)}</h1>
    <p class="article-dek">{html.escape(m.description)}</p>
    <p class="article-byline">{_dates(m)}</p>
  </header>
{_toc(toc)}
{body}
{evidence}
  <nav class="collection-pager" aria-label="Previous and next pages">{' '.join(pager)}</nav>
  <footer class="article-colophon">Part of {html.escape(m.title)}.</footer>
</main>
<script src="lib/artoo-kit/kit.js"></script>
{scripts}
</body>
</html>
"""


def render(m: Manifest, *, dry_run: bool = False) -> RenderResult:
    """Render declared Markdown content; a manifest without it keeps raw HTML."""
    if not m.content_source and not m.content_pages:
        return RenderResult("skipped")
    if m.effective_form not in {"article", "collection"}:
        return RenderResult(
            "error",
            problems=[
                f"[content] is not supported for form {m.effective_form!r}; "
                "remove [content] to author site/ HTML directly"
            ],
        )
    if not dry_run:
        m.site_dir.mkdir(parents=True, exist_ok=True)
    if m.content_source:
        source = m.dir / m.content_source
        if not source.is_file():
            return RenderResult(
                "error",
                problems=[f"content source {m.content_source} does not exist"],
            )
        dest = m.site_dir / "index.html"
        rendered = _article(m, source.read_text(encoding="utf-8"))
        if dry_run:
            return RenderResult("checked")
        dest.write_text(rendered, encoding="utf-8")
        _record_outputs(m, [dest])
        return RenderResult("written", [dest])

    root = m.dir / m.content_pages
    if not root.is_dir():
        return RenderResult("error", problems=[f"content pages directory {m.content_pages} does not exist"])
    discovered = {path.name: path for path in root.glob("*.md")}
    if m.content_order:
        missing = [name for name in m.content_order if name not in discovered]
        unlisted = sorted(set(discovered) - set(m.content_order))
        if missing or unlisted:
            detail = []
            if missing:
                detail.append("missing " + ", ".join(missing))
            if unlisted:
                detail.append("not in content.order: " + ", ".join(unlisted))
            return RenderResult(
                "error",
                problems=[f"collection page manifest does not match {m.content_pages}: " + "; ".join(detail)],
            )
        sources = [discovered[name] for name in m.content_order]
    else:
        sources = sorted(discovered.values(), key=lambda path: (path.stem != "index", path.name))
    if not sources or sources[0].stem != "index":
        return RenderResult(
            "error",
            problems=[f"content pages directory {m.content_pages} needs index.md"],
        )
    page_sources = [(path, path.read_text(encoding="utf-8")) for path in sources]
    pages = [
        (path.stem, _title(source, path.stem.replace("-", " ").title()))
        for path, source in page_sources
    ]
    written = []
    for position, (path, source) in enumerate(page_sources):
        name = "index.html" if path.stem == "index" else f"{path.stem}.html"
        dest = m.site_dir / name
        rendered = _collection_page(m, source, pages, position)
        if not dry_run:
            dest.write_text(rendered, encoding="utf-8")
            written.append(dest)
    if not dry_run:
        _record_outputs(m, written)
    return RenderResult("checked" if dry_run else "written", written)
