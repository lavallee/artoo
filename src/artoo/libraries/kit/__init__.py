"""artoo-kit: the built-in site library.

DES-governed, self-contained styling for public artifacts: a light editorial
default, an explicit dark opt-in, long-form article layout, evidence regions,
and a small component vocabulary. System font stacks only — a page using the
kit renders from file:// with zero external requests.

Behaviour ships alongside the styling: ``kit.js`` for the nav, ``provenance.js``
for the evidence panel, and ``store.js`` for ``ArtooStore``, the client that
lets a page save named JSON documents through ``artoo serve`` instead of into
browser storage nobody can review.

``CLASSES`` below is the kit's public vocabulary, and it is load-bearing in
three places: ``artoo docs artoo-kit`` prints it, ``artoo init`` writes it
into the artifact's ``AGENTS.md``, and a test asserts it matches the
stylesheets exactly. Add a public class to the CSS without adding it here and
the suite fails — which is the point. Undocumented vocabulary is vocabulary
the next author has to reverse-engineer from the stylesheet.
"""

from pathlib import Path

from .. import Library

VERSION = "0.4.0"

# Class prefixes the kit owns outright. A class starting with one of these
# that the stylesheet does not define is a guess, not an authorial choice, so
# `artoo build` reports it. Generic component names (`card`, `stat`, `toc`)
# are deliberately *not* namespaces: an artifact's own `.card-hero` is its
# business, and flagging it would train authors to ignore the check.
NAMESPACES = ("article-", "provenance")

CLASSES = {
    # Layout — the article grid and its escape hatches.
    "article": "the long-form grid container; children sit in the prose column by default",
    "article-full": "wrapper: let this child run edge to edge",
    "article-breakout": "wrapper: wider than prose, still centered",
    "article-mrow": "row that pairs a prose block with a margin note",
    # Masthead and title block.
    "article-masthead": "top bar; `__name` is the artifact link, `__label` the standfirst tag",
    "article-header": "the title block at the head of the piece",
    "article-kicker": "small label above the title (conventionally the artifact kind)",
    "article-title": "the h1",
    "article-dek": "standfirst under the title",
    "article-byline": "publication line; wrap the date in `<time datetime=…>`",
    "article-lede": "opening paragraph, set larger",
    # Evidence regions.
    "article-figure": "figure wrapper for a table or chart; put vintage, denominator, and source in the `figcaption`",
    "article-marginnote": "right-gutter note, inline on mobile; `--def`, `--source`, `--callout` variants, `.term` for the term defined",
    "article-pullquote": "breakout-width quote; attribute it with `<cite>`",
    "article-pullnumber": "breakout-width figure; `.num` is the value, `.label` its caption",
    "article-colophon": "how-it-was-made block closing the piece",
    # Components — usable on any page, article or not.
    "site-nav": "multi-page nav bar; `.brand`, `a[aria-current=\"page\"]`, `.nav-toggle` (wired by kit.js)",
    "page": "container for a non-article page; `--narrow` tightens it",
    "card-grid": "responsive grid of cards",
    "card": "one card; `h3` heading, `p` body",
    "callout": "boxed aside with a `.callout-title`; `--warn`, `--danger`, `--success` variants",
    "badge": "inline label; `--accent`, `--success`, `--warn` variants",
    "stat-row": "row of figures",
    "stat": "one figure; `.value` then `.label`",
    "toc": "table of contents, as an ordered list",
    "diagram": "wrapper for an inline SVG or a mermaid block",
    "colophon": "build and provenance footer",
    "numeric": "tabular figures, so columns of numbers align",
    "no-print": "hide this element when the page is printed",
    # Provenance panel — hydrated, not hand-authored.
    "provenance": "the provenance panel root; mark it `data-artoo-provenance` and provenance.js fills it from data/provenance.json",
    "claim-ref": "written by provenance.js onto `[C7]`-style references; never hand-author it",
}

library = Library(
    name="artoo-kit",
    version=VERSION,
    summary="Long-form article layout, evidence regions, and the provenance panel.",
    root=Path(__file__).parent / "assets",
    namespaces=NAMESPACES,
    classes=CLASSES,
)
