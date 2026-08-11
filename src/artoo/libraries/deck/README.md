# artoo-deck

Slide machinery for `kind = "presentation"` artifacts. Vendored into an
artifact at `site/lib/artoo-deck/` with a pinned hash; `artoo lib update
artoo-deck` is the explicit upgrade boundary.

| file | role |
|------|------|
| `deck.css` | chrome, slide machinery, content vocabulary, landscape print |
| `deck.js` | navigation, overview, notes, keyboard and touch control |
| `favicon.svg` | default icon |

## The `deck-` prefix is load-bearing

A deck's chrome and its content live in one stylesheet. An unprefixed chrome
class captures content that happens to use the same word — a `.bar` fixed
header will set `height: 46px` on an SVG `<rect class="bar">` and collapse a
chart. Every class here is prefixed so the two vocabularies cannot reach each
other. Keep your own content classes out of the `deck-` namespace and neither
can break the other.

## Markup contract

`deck.js` reads structure from the markup rather than from configuration:

```html
<body class="deck-root">
  <header class="deck-bar">
    <button data-deck-toggle="overview" aria-pressed="false">Overview</button>
    <button data-deck-toggle="notes" aria-pressed="false">Notes</button>
    <nav class="deck-pager">
      <button data-deck-prev>&lsaquo;</button>
      <span data-deck-counter>1 / 1</span>
      <button data-deck-next>&rsaquo;</button>
    </nav>
  </header>
  <div class="deck-progress"><i data-deck-progress></i></div>

  <main class="deck-stage" data-deck>
    <section class="deck-slide" data-act="Opening" data-short="Title">
      <div class="deck-inner">
        …
        <aside class="deck-notes"><b>Speaker note</b><p>…</p></aside>
      </div>
    </section>
  </main>

  <div class="deck-overview" data-deck-overview></div>
</body>
```

- `data-act` groups slides into acts in the overview; `data-short` labels one.
- Slides are deep-linkable: `#4` opens slide four.
- With JavaScript off every slide remains in the document and printing still
  produces the whole deck.

## Printing

`@page` is A4 landscape, one slide per page, speaker notes included — a
printed deck is usually the one being spoken from. Suppress them with
`.deck-notes { display: none }` in the artifact's own stylesheet.

Name the deck in the running foot by setting the token:

```css
.deck-root { --deck-print-id: "Acme — Q3 review ·"; }
```

## Restyling

Tokens on `.deck-root` (`--deck-accent`, `--deck-paper`, `--deck-ink`, the
font stacks) are redefinable from the artifact's own stylesheet. Charts and
bespoke slide components belong there too, not here.
