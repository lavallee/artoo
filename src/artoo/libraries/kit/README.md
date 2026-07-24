# artoo-kit

The built-in site library: DES-governed, self-contained styling for public
artifacts. Vendored into an artifact at `site/lib/artoo-kit/` with a pinned
hash — changing the kit here does not rewrite already-vendored bytes; `artoo
lib update artoo-kit` is the explicit upgrade boundary.

Files (all under `assets/`, all vendored):

| file | role |
|------|------|
| `tokens.css` | design tokens: color, type roles, spacing, the chart palette |
| `base.css` | resets and page defaults |
| `article.css` | long-form article grid (prose + margin gutter) |
| `components.css` | nav, cards, callouts, badges, stats, colophon, provenance |
| `kit.js` | theme toggle, mobile nav, optional mermaid boot |
| `provenance.js` | provenance panel hydration + in-prose claim anchors |
| `favicon.svg` | default site icon (link it to silence the `/favicon.ico` 404) |

## Favicon

Every page should carry a favicon; without one the browser requests
`/favicon.ico` and logs a 404 on every load. Reference the vendored icon in
`<head>`:

```html
<link rel="icon" href="lib/artoo-kit/favicon.svg">
```

## Provenance panel

The panel renders a flip notebook's lineage — sources with grades and
independence, claims with status and verification-method badges, counts, and
the notebook vintage — from `site/data/provenance.json` (the `flip-render/1`
projection that `artoo build` / `artoo provenance` writes from an attached
notebook).

It is **progressive**: with no projection present the panel hides itself and
the page reads exactly as authored. To add it to a hand-authored page:

```html
<!-- where the panel should appear -->
<section class="provenance article-full" data-artoo-provenance></section>

<!-- before </body>: the offline data global, then the hydrator -->
<script src="data/provenance.js"></script>
<script src="lib/artoo-kit/provenance.js"></script>
```

`data/provenance.js` sets `window.__ARTOO_PROVENANCE__` so the panel hydrates
from a `file://` URL with no server (a bare `fetch()` of a sibling JSON is
blocked under `file://`; a `<script>` assignment is not). If you omit it, the
hydrator falls back to `fetch("data/provenance.json")`, which works over HTTP.
Both files are written by `artoo provenance`; if there is no attached notebook
they do not exist, so only wire the panel on artifacts that have one.

### Claim anchors

`provenance.js` also rewrites `[C7]` / `[A3]` bracket references **that exist
in the projection** into stable anchors: the first occurrence gets
`id="claim-C7"` and every occurrence links to its entry in the panel
(`#prov-claim-C7`), with the claim text and status in a tooltip. Ids the
projection does not know are left untouched, and text inside `<code>`/`<pre>`
is never rewritten. Scope defaults to `[data-claim-anchors]`, then `<main>`,
then the body — put `data-claim-anchors` on the article element to bound it.

This is done client-side, matching the kit's existing client-side enhancements
(theme, nav, mermaid). Nothing rewrites the committed HTML; the anchors are an
enhancement layered at load time.

## Gotchas

### SVG and CSS custom properties

`fill="var(--accent)"` **does not resolve** — SVG presentation *attributes* are
not CSS and custom properties are not looked up there. Style SVG with CSS
instead: give shapes classes and set `fill` in a `<style>` block or a
stylesheet.

```html
<!-- broken: attribute never resolves the token -->
<rect fill="var(--chart-1)" .../>

<!-- works: class + CSS property -->
<style>.bar-1 { fill: var(--chart-1); }</style>
<rect class="bar-1" .../>
```

(An inline `style="fill: var(--chart-1)"` attribute also works, because that is
the CSS `fill` *property*, not the SVG presentation attribute.)

### Charts and figures

The kit ships no chart primitive; author charts as inline SVG (self-contained,
no runtime) or as a Mermaid diagram. Guidance:

- **Palette.** Use the Okabe–Ito tokens `--chart-1 … --chart-8` (in
  `tokens.css`); they are colorblind-safe and ordered by draw order. Do not
  invent per-chart colors.
- **Theme.** Because token colors differ between light and dark, style series
  with the classes-plus-`<style>` pattern above so a chart follows the theme;
  never bake a hex value that only reads in one theme.
- **Numerics.** Use `font-variant-numeric: tabular-nums` (the `--font-numeric`
  role sets it) so figures align.
- **Honesty.** A figure earns its place by helping the reader make a valid
  comparison — include vintages, denominators, and a source note in the
  `<figcaption>`, per the DES contract.
