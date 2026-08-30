# artoo-grid

Dense comparison tables for artifacts whose evidence is a few hundred entities
across a few dozen measures. Vendored into an artifact at
`site/lib/artoo-grid/` with a pinned hash; `artoo lib update artoo-grid` is the
explicit upgrade boundary.

| file | role |
|------|------|
| `grid.js` | the `ArtooGrid` wrapper: column specs, formats, toolbar, domains |
| `grid.css` | the artoo-kit-token theme over Tabulator's structural stylesheet |
| `tabulator.min.js` | vendored Tabulator 6.3.1 (MIT), virtual scroll and frozen columns |
| `tabulator.min.css` | Tabulator's structural stylesheet |

Load Tabulator before the wrapper:

```html
<link rel="stylesheet" href="lib/artoo-grid/tabulator.min.css">
<link rel="stylesheet" href="lib/artoo-grid/grid.css">
<script src="lib/artoo-grid/tabulator.min.js"></script>
<script src="lib/artoo-grid/grid.js"></script>
```

## Declaring a grid

```js
ArtooGrid.create("#table", {
  data: rows,
  index: "id",
  columns: [
    { field: "rank", title: "#",        format: "rank", frozen: true, width: 52 },
    { field: "name", title: "District", format: "name", frozen: true, sub: "county" },
    { field: "hhi",  title: "Median household income",
      group: "Means",       format: "currency", bar: true },
    { field: "prof", title: "Proficient",
      group: "Achievement", format: "percent",  heat: true, decimals: 1 },
    { field: "move", title: "Δ rank",   format: "delta", invert: true },
  ],
  toolbar: { search: true, columns: true, download: "districts.csv" },
  note: "ACS 2020-2024 · NJDOE 2024-25 · missing values shown as —, never as 0",
});
```

### Column keys

| key | meaning |
|-----|---------|
| `field`, `title` | the data key and its header |
| `format` | `text` `name` `chip` `number` `currency` `percent` `rank` `delta` |
| `group` | column-group header; consecutive columns sharing one are grouped |
| `decimals`, `scale` | number precision; `scale: 100` for a 0-1 fraction in `percent` |
| `bar` | proportional background bar, domain from the data |
| `heat` | percentile tint, domain from the data |
| `invert` | for `delta`: up is bad, so colour by meaning not by sign |
| `invertHeat` | for `heat`: low values are the notable ones |
| `frozen` | pin to the left; frozen columns are not hideable |
| `hidden` | ship the column, start it off |
| `sub` | for `name`: a second field rendered smaller beneath the label |
| `missingLabel` | override the em dash for this column |

### Two rules the grid will not let you break

**Missing is not zero.** `null`, `undefined`, `NaN` and `""` all render as an
em dash in `.grid-missing`, in every format, and that is not configurable. A
grid that lets a caller print `0` for a value nobody measured will eventually
do it by accident, and in a ranking a zero that should have been a blank is the
most expensive kind of wrong number. A row carrying `<field>_state ===
"suppressed"` says *suppressed* instead, because a value withheld by a
publisher and a value never collected are different facts.

**Blanks sort to the bottom, both directions.** A district with no measurement
has not scored zero and must never top a ranking by ascending sort.

### Domains are recomputed, never cached

`bar` and `heat` derive their scale from the data each time `setData` runs. A
table that reranks on a slider therefore rescales honestly instead of comparing
today's numbers against yesterday's maximum — a stale bar looks like a
measurement and is an artefact.

## Live reranking

```js
const grid = ArtooGrid.create("#table", { … });
slider.addEventListener("input", () => {
  grid.updateRows(rescore(rows, readWeights()));  // keeps scroll and sort
});
```

`setData` replaces the row set and redraws; `updateRows` updates in place and
holds the viewport, which is what a weight slider wants. Both rescale the
derived visuals.

## Saving what the reader configured

Pair it with `ArtooStore` from artoo-kit, which writes named JSON documents
into the artifact's `state/` directory through `artoo serve` — real files
outside `site/`, so the deploy firewall never publishes them and a diff shows
what changed:

```js
const presets = ArtooStore.open("presets");
await presets.save("means-heavy", weights);
```

With nothing serving the artifact it falls back to `localStorage` and reports
`durable === false`; print `presets.describe()` rather than let a reader
believe a save reached disk when it did not.

## The `grid-` prefix

Every class this library defines is prefixed `grid-`, and a test enforces it.
Tabulator's own `tabulator-*` classes are restyled in `grid.css` against the
artoo-kit tokens, but they are Tabulator's vocabulary, not this library's
contract — never write one by hand.

## Licence

Tabulator is MIT-licensed, © Oli Folkerd. The vendored files are unmodified
`tabulator-tables@6.3.1` dist builds.
