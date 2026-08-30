# Kinds and presentation forms

Artoo keeps two decisions separate:

- `kind` says what the artifact is about: report, explainer, research review,
  reference guide, walkthrough, case study, explorer, presentation, or note.
- `form` says how a reader uses it: article, explorer, collection, or deck.

This keeps taxonomy useful without turning it into a template gate. A report
can be an article, an interactive explorer, or a deck. `artoo init` infers the
common form from kind; `--form` overrides it.

## Article

`[content] source = "content.md"` renders a deterministic shell, title and
update metadata, TOC, section anchors, optional evidence panel, and colophon
around conservative Markdown. Delete the `[content]` table when the artifact
needs hand-authored HTML; Artoo then leaves `site/` alone.

## Explorer

The starter includes `artoo-controls`: search, declared filters, active chips,
result counts, reset, URL state, CSV, an accessible empty state, and optional
saved views. It also declares a `[[data]]` pack so the same JSON works over HTTP
and `file://`. Add `artoo-grid` when the evidence is a dense comparison table;
controls and grid remain separate because many explorers render maps, lists,
or custom figures instead.

## Collection

`[content] pages = "content"` renders each top-level Markdown file as a page;
`order = ["index.md", "evidence.md"]` is its page manifest. `index.md` is
required. Navigation, current-page state, breadcrumbs, and previous/next links
derive from that order. Missing or unlisted pages fail the build rather than
silently disappearing from navigation. Older declarations without `order`
fall back to index-first alphabetical order. Artoo records the HTML files it
generated in `work/artoo-content.json`, so a renamed page removes its stale
generated output without touching hand-authored files in `site/`.

## Deck

The deck scaffold owns one-frame-at-a-time reading, acts, speaker notes,
overview, keyboard and touch navigation, and landscape print. It remains raw
HTML because slide composition is intentionally spatial.
