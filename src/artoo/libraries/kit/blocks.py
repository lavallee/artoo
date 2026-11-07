"""Markdown blocks that render artoo-kit vocabulary.

Each renderer emits only classes ``kit/__init__.py`` documents; a test renders
every example and runs it through the invented-class check, so a block cannot
drift from the stylesheet any more than a hand-written page can.
"""

from __future__ import annotations

import re

from ...blocks import Attr, Block, Call, esc

_CARD = re.compile(r"^\[([^\]]+)\]\(([^)\s]+)\)\s*(?:[—–:-]\s*(.*))?$")


def _callout(call: Call) -> str:
    variant = call.get("variant", "note")
    cls = "callout" if variant == "note" else f"callout callout--{variant}"
    title = call.get("title")
    head = f'<strong class="callout-title">{call.inline(title)}</strong>' if title else ""
    body = call.markdown()
    if not body and not title:
        call.error("is empty; give it a title= or a body")
        return ""
    return f'<aside class="{cls}">{head}{body}</aside>'


def _stats(call: Call) -> str:
    cells = []
    for offset, line in call.lines():
        if "|" not in line:
            call.error(f"line {line!r} needs `value | label`", offset)
            continue
        value, label = (part.strip() for part in line.split("|", 1))
        cells.append(
            f'<div class="stat"><span class="value">{call.inline(value)}</span>'
            f'<span class="label">{call.inline(label)}</span></div>'
        )
    if not cells:
        call.error("has no figures; write one `value | label` line per figure")
        return ""
    if len(cells) > 6:
        call.error("holds more than 6 figures; a stat row past six stops being scannable — "
                   "use a table or a grid block")
        return ""
    return f'<div class="stat-row">{"".join(cells)}</div>'


def _pullquote(call: Call) -> str:
    text = " ".join(line for _, line in call.lines())
    if not text:
        call.error("is empty; put the quotation between the fences")
        return ""
    cite = call.get("cite")
    cite_html = f"<cite>{call.inline(cite)}</cite>" if cite else ""
    return f'<blockquote class="article-pullquote"><p>{call.inline(text)}</p>{cite_html}</blockquote>'


def _pullnumber(call: Call) -> str:
    label = " ".join(line for _, line in call.lines())
    if not label:
        call.error("needs a label: one line saying what the number counts")
        return ""
    return (
        f'<div class="article-pullnumber"><span class="num">{esc(call.get("value"))}</span>'
        f'<span class="label">{call.inline(label)}</span></div>'
    )


def _figure(call: Call) -> str:
    body = call.markdown()
    if not body:
        call.error("is empty; put the table, image or block it captions inside")
        return ""
    caption = call.get("caption")
    source = call.get("source")
    parts = []
    if caption:
        parts.append(call.inline(caption))
    if source:
        parts.append(f"Source: {call.inline(source)}")
    figcaption = f"<figcaption>{' '.join(parts)}</figcaption>" if parts else ""
    # A Markdown image paragraph is already its own figure; unwrap it so the
    # caption attaches to one figure, not a figure inside a figure.
    inner = re.sub(r'^<figure class="article-figure">(.*)</figure>$', r"\1", body, flags=re.S)
    return f'<figure class="article-figure">{inner}{figcaption}</figure>'


def _width(cls: str):
    def render(call: Call) -> str:
        body = call.markdown()
        if not body:
            call.error("is empty")
            return ""
        return f'<div class="{cls}">{body}</div>'

    return render


def _cards(call: Call) -> str:
    cards = []
    for offset, line in call.lines():
        match = _CARD.match(line.lstrip("-* ").strip())
        if not match:
            call.error(f"line {line!r} needs `[Title](page.html) — one-line description`", offset)
            continue
        title, href, description = match.groups()
        desc = f"<p>{call.inline(description)}</p>" if description else ""
        cards.append(f'<a class="nav-card" href="{esc(href)}"><h3 data-toc="skip">{call.inline(title)}</h3>{desc}</a>')
    if not cards:
        call.error("has no cards; write one `[Title](page.html) — description` line per card")
        return ""
    return f'<nav class="card-grid" aria-label="{esc(call.get("label", "Pages"))}">{"".join(cards)}</nav>'


def _lede(call: Call) -> str:
    text = " ".join(line for _, line in call.lines())
    if not text:
        call.error("is empty")
        return ""
    return f'<p class="article-lede">{call.inline(text)}</p>'


BLOCKS = (
    Block(
        name="callout",
        library="artoo-kit",
        summary="a boxed aside for a caveat, warning or result the reader must not miss",
        render=_callout,
        attrs=(
            Attr("variant", "tone", choices=("note", "warn", "danger", "success")),
            Attr("title", "bold first line"),
        ),
        positional="variant",
        example='::: callout warn title="The denominator changed"\n'
        "Counts before 2024 exclude charter schools.\n:::",
    ),
    Block(
        name="stats",
        library="artoo-kit",
        summary="a row of 2–6 headline figures, one `value | label` line each",
        render=_stats,
        body="lines",
        example="::: stats\n$4.2M | spent in 2025\n38% | of it on staffing\n12 | vendors\n:::",
    ),
    Block(
        name="pullquote",
        library="artoo-kit",
        summary="a breakout-width quotation; attribute it with cite=",
        render=_pullquote,
        attrs=(Attr("cite", "who said it, and where"),),
        body="lines",
        example='::: pullquote cite="Superintendent, board minutes, March 2025"\n'
        "We were budgeting for a district that no longer exists.\n:::",
    ),
    Block(
        name="pullnumber",
        library="artoo-kit",
        summary="one large figure with its label, breakout width",
        render=_pullnumber,
        attrs=(Attr("value", "the figure, formatted as it should read", required=True),),
        body="lines",
        example='::: pullnumber value="1 in 7"\nbuilds failed to launch with no checks at all\n:::',
    ),
    Block(
        name="figure",
        library="artoo-kit",
        summary=(
            "caption and source for whatever it wraps — a pipe table, an image, a grid or "
            "html block; state vintage and denominator in the caption"
        ),
        render=_figure,
        attrs=(
            Attr("caption", "what the reader is looking at, with vintage and denominator"),
            Attr("source", "where the figures come from"),
        ),
        example='::: figure caption="Spending by category, FY2025 (USD)" source="District ledger"\n'
        "| Category | Amount |\n|---|---:|\n| Staffing | 1,600,000 |\n:::",
    ),
    Block(
        name="wide",
        library="artoo-kit",
        summary="let its contents run wider than the prose column (breakout width)",
        render=_width("article-breakout"),
        example="::: wide\n| A | B | C | D | E | F |\n|---|---|---|---|---|---|\n"
        "| 1 | 2 | 3 | 4 | 5 | 6 |\n:::",
    ),
    Block(
        name="full",
        library="artoo-kit",
        summary="let its contents run edge to edge",
        render=_width("article-full"),
        example="::: full\n![Panorama of the site](assets/panorama.png)\n:::",
    ),
    Block(
        name="cards",
        library="artoo-kit",
        summary="navigation cards to other pages, one `[Title](page.html) — description` line each",
        render=_cards,
        attrs=(Attr("label", "accessible name for the group (default: Pages)"),),
        body="lines",
        example="::: cards\n[Method](method.html) — how the figures were built\n"
        "[Data](data.html) — every table, downloadable\n:::",
    ),
    Block(
        name="lede",
        library="artoo-kit",
        summary="the opening paragraph, set larger",
        render=_lede,
        body="lines",
        example="::: lede\nThe district spent more on substitutes than on textbooks.\n:::",
    ),
)
