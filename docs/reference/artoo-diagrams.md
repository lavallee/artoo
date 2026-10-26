# artoo-diagrams 1.10.1+artoo.1

Mermaid-syntax diagrams rendered offline by Pele 1.10.1: flowcharts, sequences, state, ER, timelines, and more, following the page's theme.

Mermaid-syntax diagrams that render offline, in the page's own type and
colors. Vendored into an artifact at `site/lib/artoo-diagrams/` with a pinned
hash; `artoo lib update artoo-diagrams` is the explicit upgrade boundary.

You write [Mermaid](https://mermaid.js.org) syntax. The renderer is
[Pele](https://pele.run), which draws every diagram type built into Mermaid
12.1 with its own layout and reads its colors from CSS, so a diagram recolors
when the reader switches theme instead of being redrawn.

| file | role |
|------|------|
| `pele.global.js` | Pele's browser bundle (MIT), byte for byte as published on npm |
| `diagrams.js` | finds Mermaid blocks, renders them with Pele, reports errors |
| `diagrams.css` | binds Pele's colors and fonts to the artoo-kit tokens; node roles |
| `PELE-LICENSE` | Pele's license |

## Use it

Markdown content needs nothing: a ` ```mermaid ` fence in an article or
collection page renders as a diagram, and `artoo build` vendors this library
the first time a page needs it.

Hand-written HTML vendors the library once:

```bash
artoo lib add artoo-diagrams
```

then loads it on each page that has a diagram, and only those (the bundle
is about 700 KB):

```html
<link rel="stylesheet" href="lib/artoo-diagrams/diagrams.css">
...
<script src="lib/artoo-diagrams/pele.global.js"></script>
<script src="lib/artoo-diagrams/diagrams.js"></script>
```

and writes each diagram as a source block inside the kit's `diagram`
wrapper:

```html
<figure class="diagram">
<pre class="mermaid">flowchart LR
  accTitle: How a build gates publication
  accDescr: Content is rendered, checked by the firewall, then verified.
  render[Render content] --> firewall{{Publish firewall}}:::accent --> verify[Verify]
</pre>
  <figcaption>The takeaway, in a sentence.</figcaption>
</figure>
```

Rendering waits for the document, so the two scripts can sit anywhere in
either order. With JavaScript off, the reader sees the source.

## Write diagrams that hold up

- **Use a diagram for structure, inline SVG for numbers.** Flows, sequences,
  states, schemas, architecture, and timelines are what diagrams are for. A
  chart that carries a quantitative claim belongs in inline SVG on the
  `--chart-*` palette, with its vintage, denominator, and source in the
  `figcaption`. Pie, XY, and quadrant charts are fine for sketches.
- **Start with `accTitle:` and `accDescr:`.** They become the SVG's
  accessible name and description. The `figcaption` carries the point.
- **Name a role, never a color.** Mermaid `style`, `classDef`, and `linkStyle`
  take literal colors, which stay fixed when the theme changes, and the parser
  rejects `var(--token)` there. Tag the node instead, and the color comes from
  the kit:

  | role | use |
  |------|-----|
  | `accent` | the node the diagram is about: a gate, a decision, the subject |
  | `warn` | a failure path or a risk |
  | `muted` | context: out of scope, deprecated, external |

  Write `id[Label]:::accent`, or `class a,b muted` for several nodes. For a
  role of your own, tag `:::name` and style it in your stylesheet with tokens,
  e.g. `.mermaid .pele-node.name > :not(text) { stroke: var(--success); }`.
- **Escape `<`, `>`, and `&` in hand-written HTML.** The block's text is the
  source, so write `A[List&lt;T&gt;]`. Markdown fences need no escaping.
- **Let wide diagrams leave the prose column.** In an article, put
  `article-breakout` on the figure (`class="diagram article-breakout"`).
  Below 640 px a left-to-right flowchart turns vertical, and a diagram that
  had to shrink gets zoom controls, so write one that reads in either
  direction.
- **Leave out what Pele does not render.** HTML labels, `click` callbacks,
  Mermaid themes and `themeVariables`, ZenUML, and other external Mermaid
  plugins are not supported. Labels support line breaks, bold, and italic.
- **One diagram, one idea.** Past a dozen or so nodes, split it, or use
  `artoo-map` for a code graph a reader should explore.

## Check it

A syntax error is drawn in place of the diagram, and `diagrams.js` logs it to
the console with the block's id (or position), the line and column, and the
offending line. `artoo verify --browser` reports those messages, so give
diagrams an `id` when a page has several.

`artoo build` fails a page that has a Mermaid block but does not load
`pele.global.js` and `diagrams.js`, because that page would ship a wall of
source text.

## Diagrams added after load

An explorer that inserts diagram source at runtime calls
`ArtooDiagrams.render(element)` to render the blocks inside `element`. It
returns Pele's mounted diagrams; each re-fits itself when its container
resizes.

## Versions and mermaid.js

The library's version is `<pele version>+artoo.<revision>`, so `artoo lib
status` shows which Pele an artifact carries. A newer artoo ships a newer Pele;
your artifact keeps its pinned copy until you run `artoo lib update
artoo-diagrams`. Look at the page after updating: Pele's layout still changes
between minor releases.

If you need mermaid.js itself, for HTML labels or an external Mermaid plugin,
install the separate `artoo-mermaid` library and load `mermaid.min.js` with
the kit's `kit.js` instead. Use one renderer per page.

## Class vocabulary

| class | role |
|---|---|
| `mermaid` | a Mermaid source block (`<pre class="mermaid">`); diagrams.js replaces it with the rendered diagram, themed from the kit's tokens |
