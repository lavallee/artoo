# artoo-deck 0.1.0

Slides: acts, speaker notes, overview, keyboard/touch nav, landscape print.

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

## Class vocabulary

| class | role |
|---|---|
| `deck-root` | on `<body>`; carries the deck's redefinable `--deck-*` tokens |
| `deck-bar` | fixed top chrome holding the mark, toggles, and pager |
| `deck-mark` | the initial or logo mark in the bar |
| `deck-who` | the deck's name in the bar |
| `deck-spacer` | flexible gap pushing bar items apart |
| `deck-pager` | prev / counter / next group in the bar |
| `deck-pager-m` | the mobile pager, shown only on narrow screens |
| `deck-counter` | slide counter; deck.js writes into `[data-deck-counter]` |
| `deck-progress` | progress rail; its inner `<i data-deck-progress>` is the fill |
| `deck-stage` | slide container; must carry `data-deck` for deck.js to find it |
| `deck-slide` | one slide; `data-act` groups it in the overview, `data-short` labels it |
| `deck-inner` | the slide's content box, centered and width-capped |
| `deck-eyebrow` | small rule-trailing label above the slide heading |
| `deck-lede` | opening line on a title slide |
| `deck-notes` | speaker note; hidden until toggled, and printed with the slide |
| `deck-stat-row` | row of figures on a slide |
| `deck-stat` | one figure; `<b>` the value, `<span>` its label |
| `deck-grid` | ruled column layout; add `two`, `three`, or `four` |
| `deck-cell` | one cell of a `deck-grid`; `<b>` heading, `<p>` body |
| `deck-facts` | ruled key/value list; `.k` is the key, `.v` the value |
| `deck-callout` | the sentence you want repeated back to you; `cool` tints it |
| `deck-figure` | figure on a slide; a direct child `<svg>` is sized to fit |
| `deck-table-wrap` | scroll container for a table too wide for the frame |
| `deck-overview` | overview panel root; mark it `data-deck-overview` and deck.js fills it |
| `deck-ov-act` | one act group inside the overview (generated) |
| `deck-ov-grid` | the slide grid within an act (generated) |
| `deck-ov-item` | one slide thumbnail in the overview (generated) |
| `deck-help` | keyboard-help overlay; mark it `data-deck-help` |
| `deck-help-card` | the card inside the help overlay |

artoo-deck owns `deck-`. A class starting with one of those that the vendored stylesheet does not define is a guess, and `artoo build` reports it with the nearest real class. Your own classes belong outside those prefixes.
