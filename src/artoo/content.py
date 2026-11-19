"""Deterministic Markdown rendering for article and collection forms."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from . import blocks as blocks_mod
from . import libraries
from . import sourcemap as sourcemap_mod
from .generators.notebook_report import markdown
from .manifest import Manifest

_H1 = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.MULTILINE)
# Only headings the Markdown renderer wrote (bare, or carrying a source-map id);
# a heading inside a `::: html` island keeps its own markup and stays off the TOC.
_HEADING = re.compile(r'<(h[23])( data-artoo-src="a\d+")?>(.*?)</\1>')
_TAGS = re.compile(r"<[^>]+>")
_OUTPUTS = "artoo-content.json"
# A ```mermaid fence becomes the source block artoo-diagrams renders, the same
# markup an author writes by hand, so there is one diagram contract, not two.
_MERMAID_FENCE = re.compile(
    r'<pre( data-artoo-src="a\d+")?><code class="language-mermaid">(.*?)</code></pre>', re.S
)
DIAGRAMS = "artoo-diagrams"
DIAGRAM_STYLES = '<link rel="stylesheet" href="lib/artoo-diagrams/diagrams.css">'
DIAGRAM_SCRIPTS = (
    '<script src="lib/artoo-diagrams/pele.global.js"></script>\n'
    '<script src="lib/artoo-diagrams/diagrams.js"></script>'
)


@dataclass
class RenderResult:
    status: str
    written: list[Path] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


_FRONT = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
FRONT_KEYS = ("description", "kicker", "image", "image_alt", "label", "evidence")


def _front(source: str) -> tuple[dict[str, str], str]:
    """Optional page front matter: ``key: value`` lines between ``---`` fences at the top.

    Known keys: ``description`` (the page's dek and meta description, instead of the
    manifest's), ``kicker`` (instead of the kind), ``image`` (a site-relative social
    card: og:image and a large Twitter card), ``image_alt``, ``label`` (a short name
    for the page in collection navigation, breadcrumb and previous/next links,
    instead of its title) and ``evidence`` (notebook ids the page answers or asserts,
    checked when the source map carries evidence). Unknown keys are kept
    in the dict and ignored, so drafts can carry their own notes."""
    match = _FRONT.match(source)
    if not match:
        return {}, source
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    # Blank lines stand in for the front matter so block errors keep reporting
    # the line number an editor shows.
    return meta, "\n" * match.group(0).count("\n") + source[match.end():]


def _social(title: str, description: str, meta: dict[str, str]) -> str:
    """Open Graph and Twitter tags for a page with a front-matter ``image``."""
    if not meta.get("image"):
        return ""
    tags = [
        f'<meta property="og:title" content="{html.escape(title, quote=True)}">',
        f'<meta property="og:description" content="{html.escape(description, quote=True)}">',
        f'<meta property="og:image" content="{html.escape(meta["image"], quote=True)}">',
        '<meta name="twitter:card" content="summary_large_image">',
    ]
    if meta.get("image_alt"):
        tags.append(f'<meta property="og:image:alt" content="{html.escape(meta["image_alt"], quote=True)}">')
    return "\n".join(tags) + "\n"


def _title(source: str, fallback: str) -> str:
    match = _H1.search(source)
    return match.group(1).strip() if match else fallback


def _without_first_h1(source: str) -> str:
    # Blanked rather than removed, for the same reason as front matter.
    return _H1.sub("", source, count=1)


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


def _context(m: Manifest, source_name: str) -> blocks_mod.Context:
    site = m.site_dir

    def poster_exists(rel: str) -> bool:
        return not rel.startswith(("http:", "https:", "/")) and (site / rel).is_file()

    return blocks_mod.Context(
        registry=blocks_mod.registry(),
        source=source_name,
        data_packs=m.data_packs,
        artifact_dir=m.dir,
        poster_exists=poster_exists,
    )


def _body_and_toc(
    source: str, ctx: blocks_mod.Context, marks: sourcemap_mod.PageMap | None = None
) -> tuple[str, list[tuple[int, str, str]]]:
    fragment = _MERMAID_FENCE.sub(
        lambda m: f'<pre class="mermaid"{m.group(1) or ""}>{m.group(2)}</pre>',
        markdown.to_html(
            _without_first_h1(source), poster_exists=ctx.poster_exists, blocks=ctx, marks=marks
        ),
    )
    used: set[str] = set()
    toc: list[tuple[int, str, str]] = []

    def add_id(match: re.Match) -> str:
        tag = match.group(1)
        text = match.group(3)
        anchor = _slug(text, used)
        # The heading is already escaped HTML; _toc escapes the label, so store it plain.
        toc.append((int(tag[1]), html.unescape(_TAGS.sub("", text)), anchor))
        return f'<{tag} id="{anchor}"{match.group(2) or ""}>{text}</{tag}>'

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


def _has_diagram(body: str) -> bool:
    return 'class="mermaid"' in body


def _ensure_block_libraries(m: Manifest, ctx: blocks_mod.Context) -> None:
    """Vendor what a block needs the first time it is used; never re-vendor."""
    recorded = {entry.get("name") for entry in m.libraries}
    for name in ctx.libraries:
        if name not in recorded:
            libraries.add(m, name)


def _ensure_diagrams(m: Manifest) -> None:
    """Vendor artoo-diagrams the first time content needs it; never re-vendor.

    An artifact that already records the library keeps the bytes it pinned:
    `artoo lib update artoo-diagrams` stays the only upgrade boundary.
    """
    if not any(entry.get("name") == DIAGRAMS for entry in m.libraries):
        libraries.add(m, DIAGRAMS)


def _head(
    m: Manifest,
    title: str,
    diagrams: bool = False,
    meta: dict[str, str] | None = None,
    styles: list[str] | None = None,
) -> str:
    meta = meta or {}
    extra = "".join(f'<link rel="stylesheet" href="{html.escape(href, quote=True)}">\n'
                    for href in styles or [])
    plain = meta.get("description") or m.description or f"{title} — {m.kind}"
    description = html.escape(plain, quote=True)
    return f"""<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{description}">
{_social(title, plain, meta)}<link rel="icon" href="lib/artoo-kit/favicon.svg">
<link rel="stylesheet" href="lib/artoo-kit/tokens.css">
<link rel="stylesheet" href="lib/artoo-kit/base.css">
<link rel="stylesheet" href="lib/artoo-kit/article.css">
<link rel="stylesheet" href="lib/artoo-kit/components.css">
{DIAGRAM_STYLES + chr(10) if diagrams else ""}{extra}</head>"""


def _html_open(m: Manifest) -> str:
    look = f' data-look="{m.look}"' if m.look and m.look != "editorial" else ""
    return f'<html lang="en" data-theme="light"{look}>'


def _scripts(ctx: blocks_mod.Context, *parts: str) -> str:
    """Block scripts first (libraries, data packs), then the page's own."""
    tags = [f'<script src="{html.escape(src, quote=True)}"></script>' for src in ctx.scripts]
    return "\n".join(part for part in (*tags, *parts) if part)


def _dates(m: Manifest) -> str:
    published = f'Published <time datetime="{m.created}">{m.created}</time>'
    if not m.updated or m.updated == m.created:
        return published
    return published + f' · Updated <time datetime="{m.updated}">{m.updated}</time>'


def _front_line(source: str, key: str) -> int | None:
    """0-based line of a front-matter key, before `_front` blanks the block."""
    match = _FRONT.match(source)
    if not match:
        return None
    found = re.search(rf"^{re.escape(key)}[ \t]*:", match.group(1), re.M)
    return sourcemap_mod.line_of(source, match.start(1) + found.start()) if found else None


def _title_line(source: str) -> int | None:
    match = _H1.search(source)
    return sourcemap_mod.line_of(source, match.start()) if match else None


def _origin_attr(pmap: sourcemap_mod.PageMap | None, kind: str, index: int | None) -> str:
    if pmap is None or index is None:
        return ""
    origin = pmap.origin_of(index)
    if origin is None or origin.file == "-":
        return ""
    return pmap.special(kind, origin.file, [origin.line, origin.line] if origin.line else None)


def _manifest_attr(pmap: sourcemap_mod.PageMap | None, kind: str, key: str) -> str:
    return pmap.special(kind, "artifact.toml", None, key) if pmap is not None else ""


def _header_marks(
    m: Manifest, source: str, pmap: sourcemap_mod.PageMap | None, title_fallback_key: str
) -> tuple[dict[str, str], str, dict[str, str]]:
    """Front matter, the source without it, and source-map attributes for the header."""
    dek_line = _front_line(source, "description")
    meta, source = _front(source)
    title_line = _title_line(source)
    attrs = {
        "title": _origin_attr(pmap, "title", title_line)
        if title_line is not None
        else (_manifest_attr(pmap, "title", title_fallback_key) if title_fallback_key else ""),
        "dek": _origin_attr(pmap, "dek", dek_line)
        if meta.get("description")
        else (_manifest_attr(pmap, "dek", "artifact.description") if m.description else ""),
        "masthead": _manifest_attr(pmap, "masthead", "artifact.title"),
    }
    return meta, source, attrs


def _article(
    m: Manifest, source: str, ctx: blocks_mod.Context, pmap: sourcemap_mod.PageMap | None = None
) -> str:
    meta, source, attrs = _header_marks(m, source, pmap, "artifact.title")
    title = _title(source, m.title)
    body, toc = _body_and_toc(source, ctx, pmap)
    evidence, scripts = _evidence(m)
    diagrams = _has_diagram(body)
    if diagrams:
        scripts = "\n".join(part for part in (DIAGRAM_SCRIPTS, scripts) if part)
    scripts = _scripts(ctx, scripts)
    return f"""<!doctype html>
{_html_open(m)}
{_head(m, title, diagrams, meta, ctx.styles)}
<body>
<header class="article-masthead">
  <a class="article-masthead__name" href="index.html"{attrs["masthead"]}>{html.escape(m.title)}</a>
  <span class="article-masthead__label">Artoo artifact</span>
</header>
<main class="article" data-claim-anchors>
  <header class="article-header">
    <div class="article-kicker">{html.escape(meta.get("kicker") or m.kind)}</div>
    <h1 class="article-title"{attrs["title"]}>{html.escape(title)}</h1>
    <p class="article-dek"{attrs["dek"]}>{html.escape(meta.get("description") or m.description)}</p>
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


def _page_href(slug: str) -> str:
    return "index.html" if slug == "index" else f"{slug}.html"


def _collection_page(
    m: Manifest,
    source: str,
    pages: list[tuple[str, str]],
    position: int,
    ctx: blocks_mod.Context,
    pmap: sourcemap_mod.PageMap | None = None,
) -> str:
    """One page of a collection. ``pages`` holds (slug, navigation label) in order."""
    slug, label = pages[position]
    meta, source, attrs = _header_marks(m, source, pmap, "")
    title = _title(source, label)
    body, toc = _body_and_toc(source, ctx, pmap)
    evidence, scripts = _evidence(m)
    diagrams = _has_diagram(body)
    if diagrams:
        scripts = "\n".join(part for part in (DIAGRAM_SCRIPTS, scripts) if part)
    block_scripts = _scripts(ctx)
    nav = "\n".join(
        "  <a{} href=\"{}\">{}</a>".format(
            ' aria-current="page"' if index == position else "",
            _page_href(page_slug),
            html.escape(page_label),
        )
        for index, (page_slug, page_label) in enumerate(pages)
    )
    previous = pages[position - 1] if position else None
    following = pages[position + 1] if position + 1 < len(pages) else None
    pager = []
    if previous:
        pager.append(f'<a rel="prev" href="{_page_href(previous[0])}">← {html.escape(previous[1])}</a>')
    if following:
        pager.append(f'<a rel="next" href="{_page_href(following[0])}">{html.escape(following[1])} →</a>')
    return f"""<!doctype html>
{_html_open(m)}
{_head(m, title, diagrams, meta, ctx.styles)}
<body>
<nav class="site-nav" aria-label="Collection">
  <a class="brand" href="index.html"{attrs["masthead"]}>{html.escape(m.title)}</a>
  <button class="nav-toggle" type="button" aria-label="Menu" aria-expanded="false">Menu</button>
  <div class="nav-links">
{nav}
  </div>
</nav>
<main class="article" data-claim-anchors>
  <nav aria-label="Breadcrumb"><a href="index.html">{html.escape(m.title)}</a> / {html.escape(label if meta.get("label") else title)}</nav>
  <header class="article-header">
    <div class="article-kicker">{html.escape(meta.get("kicker") or m.kind)}</div>
    <h1 class="article-title"{attrs["title"]}>{html.escape(title)}</h1>
    <p class="article-dek"{attrs["dek"]}>{html.escape(meta.get("description") or m.description)}</p>
    <p class="article-byline">{_dates(m)}</p>
  </header>
{_toc(toc)}
{body}
{evidence}
  <nav class="collection-pager" aria-label="Previous and next pages">{' '.join(pager)}</nav>
  <footer class="article-colophon">Part of {html.escape(m.title)}.</footer>
</main>
{block_scripts}
<script src="lib/artoo-kit/kit.js"></script>
{scripts}
</body>
</html>
"""


def _declared_evidence(source: str) -> list[str]:
    value = _front(source)[0].get("evidence", "")
    return [ref for ref in re.split(r"[\s,]+", value) if ref]


def _write_sourcemap(
    m: Manifest, maps: dict[str, sourcemap_mod.PageMap], declared: dict[str, list[str]]
) -> tuple[list[str], list[str]]:
    from . import provenance as provenance_mod

    projection = provenance_mod.read_projection(m) if (m.notebook or m.evidence_source) else None
    where = provenance_mod.projection_path(m)
    path, notes, problems = sourcemap_mod.write(
        m.dir, maps, generator=f"artoo {__version__}", declared=declared, projection=projection,
        projection_file=str(where.relative_to(m.dir)) if projection else "",
    )
    blocks = sum(len(page.blocks) for page in maps.values())
    return [f"source map: {blocks} block(s) on {len(maps)} page(s) → {path.relative_to(m.dir)}", *notes], problems


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
        ctx = _context(m, m.content_source)
        clean, origins = sourcemap_mod.split(source.read_text(encoding="utf-8"), m.content_source)
        pmap = sourcemap_mod.PageMap(m.content_source, origins) if m.content_sourcemap else None
        rendered = _article(m, clean, ctx, pmap)
        if ctx.diagnostics:
            return RenderResult("error", problems=ctx.diagnostics)
        if dry_run:
            return RenderResult("checked")
        _ensure_block_libraries(m, ctx)
        if _has_diagram(rendered):
            _ensure_diagrams(m)
        dest.write_text(rendered, encoding="utf-8")
        _record_outputs(m, [dest])
        problems: list[str] = []
        notes: list[str] = []
        if pmap is not None:
            pmap.collect_texts(rendered)
            notes, problems = _write_sourcemap(
                m, {"index.html": pmap}, {"index.html": _declared_evidence(clean)}
            )
        return RenderResult("error" if problems else "written", [dest], problems, notes)

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
    prefix = m.content_pages.rstrip("/")
    page_sources = []
    for path in sources:
        clean, origins = sourcemap_mod.split(path.read_text(encoding="utf-8"), f"{prefix}/{path.name}")
        page_sources.append((path, clean, origins))
    pages = []
    for path, clean, _origins in page_sources:
        meta, body = _front(clean)
        pages.append((path.stem, meta.get("label") or _title(body, path.stem.replace("-", " ").title())))
    written = []
    rendered_pages = []
    maps: dict[str, sourcemap_mod.PageMap] = {}
    declared: dict[str, list[str]] = {}
    problems: list[str] = []
    for position, (path, clean, origins) in enumerate(page_sources):
        name = "index.html" if path.stem == "index" else f"{path.stem}.html"
        ctx = _context(m, f"{prefix}/{path.name}")
        pmap = sourcemap_mod.PageMap(f"{prefix}/{path.name}", origins) if m.content_sourcemap else None
        rendered = _collection_page(m, clean, pages, position, ctx, pmap)
        rendered_pages.append((m.site_dir / name, rendered, ctx))
        if pmap is not None:
            pmap.collect_texts(rendered)
            maps[name] = pmap
            declared[name] = _declared_evidence(clean)
        problems.extend(ctx.diagnostics)
    if problems:
        return RenderResult("error", problems=problems)
    for dest, rendered, ctx in rendered_pages:
        if not dry_run:
            _ensure_block_libraries(m, ctx)
            if _has_diagram(rendered):
                _ensure_diagrams(m)
            dest.write_text(rendered, encoding="utf-8")
            written.append(dest)
    notes: list[str] = []
    if not dry_run:
        _record_outputs(m, written)
        if maps:
            notes, problems = _write_sourcemap(m, maps, declared)
    status = "error" if problems else ("checked" if dry_run else "written")
    return RenderResult(status, written, problems, notes)
