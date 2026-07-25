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
- inline: ``**bold**``, ``*italic*`` / ``_italic_``, ``` `code` ```, and
  ``[text](url)`` links

Deliberate non-goals (documented limits): nested lists, tables, reference-style
links, images, HTML passthrough, setext headings, footnotes. A draft that needs
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


def to_html(md: str) -> str:
    """Render a Markdown draft (the flip subset above) to an HTML fragment."""
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

        # Paragraph: gather consecutive non-blank, non-structural lines.
        para: list[str] = []
        while i < n and lines[i].strip() and not _is_block_start(lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        close_list()
        out.append(f"<p>{_inline(' '.join(para))}</p>")

    close_list()
    return "\n".join(out)


def _is_block_start(stripped: str) -> bool:
    """True when a line begins a block that must not be folded into a paragraph."""
    return bool(
        stripped.startswith(("```", ">"))
        or _HEADING.match(stripped)
        or _ULIST.match(stripped)
        or _OLIST.match(stripped)
        or _HR.match(stripped)
    )
