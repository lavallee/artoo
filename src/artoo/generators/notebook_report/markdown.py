"""A small, conservative Markdown → HTML converter.

artoo vendors no Markdown library (the explainer synthesizes HTML directly
through worker CLIs), and the read-direction ``notebook-report`` generator is
fully deterministic — it cannot shell out to a model to render a draft. So it
carries this deliberately minimal converter for the subset flip drafts use.

Supported, and nothing else:

- ATX headings ``#`` … ``######``
- paragraphs (blank-line separated)
- unordered lists (``-`` / ``*``) and ordered lists (``1.``)
- fenced code blocks (```` ``` ````), left verbatim and HTML-escaped
- blockquotes (``>``)
- thematic breaks (``---`` / ``***`` on their own line)
- inline: ``**bold**``, ``*italic*`` / ``_italic_``, ``` `code` ```,
  ``[text](url)`` links, and ``![alt](src)`` images
- figures: a paragraph that is only an image, ``![alt](src "caption")``,
  becomes ``<figure class="article-figure">`` with the optional title as its
  ``figcaption``. When ``src`` is a video (``.mp4``, ``.webm``, ``.mov``,
  ``.m4v``) the figure holds a silent loop instead: ``<video class="article-loop"
  autoplay loop muted playsinline>`` named by the alt text (``aria-label``), with
  ``poster`` from a sibling ``<stem>.poster.png`` when the renderer knows it
  exists. kit.js pauses loops for readers who prefer reduced motion.
- toggles: a ```` ```toggle ```` fence of ``Label: ![alt](src)`` lines (2–4)
  and an optional ``caption: …`` line becomes ``<figure class="article-figure
  article-toggle">``: one image shown at a time, switched by labelled radio
  buttons. Pure CSS, so it works from ``file://`` with no script.
- pipe tables: a header row, a ``---|---`` separator row (``---:`` right-aligns
  and marks the column ``numeric``), then body rows; wrapped in a focusable
  ``article-table`` region that scrolls sideways when the table is wider than
  the screen

Image sources stay local in practice: ``artoo verify`` flags missing files,
remote runtime assets, and images without ``alt``.

Deliberate non-goals (documented limits): nested lists, reference-style links,
HTML passthrough, setext headings, footnotes, table cells spanning columns. A draft that needs
those should be authored as HTML upstream. Bracketed flip ids like ``[C7]`` are
left untouched on purpose — they carry no ``(url)`` so the link rule skips them,
and the artoo-kit provenance hydrator turns them into claim anchors client-side.
"""

from __future__ import annotations

import html
import re

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_ULIST = re.compile(r"^[-*]\s+(.*)$")
_OLIST = re.compile(r"^\d+\.\s+(.*)$")
_HR = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_IMAGE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)')
_FIGURE = re.compile(r'^!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)$')


def _attr(text: str) -> str:
    """Raw Markdown text as an HTML attribute value."""
    return html.escape(text, quote=True)


def _img(alt: str, src: str) -> str:
    return f'<img src="{_attr(src)}" alt="{_attr(alt)}" loading="lazy">'


_VIDEO_EXT = (".mp4", ".webm", ".mov", ".m4v")
_VIDEO_TYPE = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}


def _is_video(src: str) -> bool:
    return src.split("?", 1)[0].split("#", 1)[0].lower().endswith(_VIDEO_EXT)


def _video(alt: str, src: str, poster: str | None = None) -> str:
    """A silent loop, named by its alt text. No controls: kit.js adds them (and
    pauses the loop) for readers who prefer reduced motion, and a click toggles it."""
    path = src.split("?", 1)[0].split("#", 1)[0].lower()
    kind = next((t for ext, t in _VIDEO_TYPE.items() if path.endswith(ext)), "video/mp4")
    poster_attr = f' poster="{_attr(poster)}"' if poster else ""
    return (f'<video class="article-loop" autoplay loop muted playsinline preload="metadata"{poster_attr} '
            f'aria-label="{_attr(alt)}"><source src="{_attr(src)}" type="{kind}"></video>')


def _poster_for(src: str, poster_exists) -> str | None:
    if poster_exists is None:
        return None
    stem = src.rsplit(".", 1)[0]
    candidate = f"{stem}.poster.png"
    return candidate if poster_exists(candidate) else None


_TOGGLE_LINE = re.compile(r'^([^:]{1,40}):\s*!\[([^\]]*)\]\(([^)\s]+)\)\s*$')
_toggle_count = 0


def _toggle(body: list[str]) -> str | None:
    """``Label: ![alt](src)`` lines (2–4) and an optional ``caption:`` → a CSS-only toggle figure."""
    global _toggle_count
    options, caption = [], None
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("caption:"):
            caption = line.split(":", 1)[1].strip()
            continue
        m = _TOGGLE_LINE.match(line)
        if not m:
            return None
        options.append(m.groups())
    if not 2 <= len(options) <= 4:
        return None
    _toggle_count += 1
    name = f"article-toggle-{_toggle_count}"
    inputs = "".join(
        f'<input type="radio" name="{name}" id="{name}-{i}"{" checked" if i == 0 else ""}>'
        for i in range(len(options)))
    labels = "".join(f'<label for="{name}-{i}">{_inline(label.strip())}</label>' for i, (label, _, _) in enumerate(options))
    panels = "".join(
        (_video(alt, src) if _is_video(src) else _img(alt, src)) for _, alt, src in options)
    cap = f"<figcaption>{_inline(caption)}</figcaption>" if caption else ""
    return (f'<figure class="article-figure article-toggle">{inputs}'
            f'<div class="article-toggle__bar" role="group" aria-label="Show">{labels}</div>'
            f'<div class="article-toggle__panels">{panels}</div>{cap}</figure>')


_TABLE_SEP = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")


def _cells(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [c.strip() for c in row.split("|")]


def _table(rows: list[str]) -> str:
    head, sep, body = _cells(rows[0]), _cells(rows[1]), [_cells(r) for r in rows[2:]]
    right = [c.endswith(":") and not c.startswith(":") for c in sep]

    def cell(tag: str, text: str, i: int, scope: str = "") -> str:
        cls = ' class="numeric"' if i < len(right) and right[i] else ""
        return f"<{tag}{scope}{cls}>{_inline(text)}</{tag}>"

    thead = "<tr>" + "".join(cell("th", c, i, ' scope="col"') for i, c in enumerate(head)) + "</tr>"
    tbody = "".join("<tr>" + "".join(cell("td", c, i) for i, c in enumerate(r)) + "</tr>" for r in body)
    # Wrapped so a wide table scrolls inside its own region instead of widening the page
    # on a phone; focusable so the scroll works from the keyboard.
    return (f'<div class="article-table" role="region" tabindex="0" aria-label="Table">'
            f"<table><thead>{thead}</thead><tbody>{tbody}</tbody></table></div>")

_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)|(?<!_)_([^_]+)_(?!_)")
_CODE = re.compile(r"`([^`]+)`")


def _inline(text: str) -> str:
    """Escape HTML, then apply inline markup. Code spans are protected first."""
    # Protect code spans from further escaping/markup by extracting them.
    spans: list[str] = []

    def _stash(match: re.Match) -> str:
        spans.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00{len(spans) - 1}\x00"

    text = _CODE.sub(_stash, text)

    def _stash_image(match: re.Match) -> str:
        spans.append(_img(match.group(1), match.group(2)))
        return f"\x00{len(spans) - 1}\x00"

    text = _IMAGE.sub(_stash_image, text)
    text = html.escape(text, quote=False)
    text = _LINK.sub(
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
        text,
    )
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(
        lambda m: f"<em>{m.group(1) or m.group(2)}</em>", text
    )
    text = re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text)
    return text


def to_html(md: str, *, poster_exists=None) -> str:
    """Render a Markdown draft (the flip subset above) to an HTML fragment.

    ``poster_exists``, when given, is called with a candidate ``<stem>.poster.png``
    path for each video figure and says whether that file exists; the renderer
    passes one that resolves against the site, the generator passes none."""
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    list_stack: str | None = None  # "ul" | "ol" | None

    def close_list() -> None:
        nonlocal list_stack
        if list_stack:
            out.append(f"</{list_stack}>")
            list_stack = None

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Fenced code block.
        if stripped.startswith("```"):
            close_list()
            lang = stripped[3:].strip()
            body: list[str] = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1  # consume the closing fence
            if lang == "toggle":
                rendered = _toggle(body)
                if rendered:
                    out.append(rendered)
                    continue
            cls = f' class="language-{html.escape(lang, quote=True)}"' if lang else ""
            code = html.escape("\n".join(body))
            out.append(f"<pre><code{cls}>{code}</code></pre>")
            continue

        if not stripped:
            close_list()
            i += 1
            continue

        if _HR.match(stripped):
            close_list()
            out.append("<hr>")
            i += 1
            continue

        heading = _HEADING.match(stripped)
        if heading:
            close_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
            i += 1
            continue

        ul = _ULIST.match(stripped)
        if ul:
            if list_stack != "ul":
                close_list()
                out.append("<ul>")
                list_stack = "ul"
            out.append(f"<li>{_inline(ul.group(1).strip())}</li>")
            i += 1
            continue

        ol = _OLIST.match(stripped)
        if ol:
            if list_stack != "ol":
                close_list()
                out.append("<ol>")
                list_stack = "ol"
            out.append(f"<li>{_inline(ol.group(1).strip())}</li>")
            i += 1
            continue

        if stripped.startswith(">"):
            close_list()
            quote: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f"<blockquote><p>{_inline(' '.join(quote))}</p></blockquote>")
            continue

        if stripped.startswith("|") and i + 1 < n and _TABLE_SEP.match(lines[i + 1].strip()):
            close_list()
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(_table(rows))
            continue

        # Paragraph: gather consecutive non-blank, non-structural lines.
        para: list[str] = []
        while i < n and lines[i].strip() and not _is_block_start(lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        close_list()
        figure = _FIGURE.match(" ".join(para))
        if figure:
            alt, src, caption = figure.groups()
            caption_html = f"<figcaption>{_inline(caption)}</figcaption>" if caption else ""
            media = _video(alt, src, _poster_for(src, poster_exists)) if _is_video(src) else _img(alt, src)
            out.append(f'<figure class="article-figure">{media}{caption_html}</figure>')
            continue
        out.append(f"<p>{_inline(' '.join(para))}</p>")

    close_list()
    return "\n".join(out)


def _is_block_start(stripped: str) -> bool:
    """True when a line begins a block that must not be folded into a paragraph."""
    return bool(
        stripped.startswith(("```", ">", "|"))
        or _HEADING.match(stripped)
        or _ULIST.match(stripped)
        or _OLIST.match(stripped)
        or _HR.match(stripped)
    )
