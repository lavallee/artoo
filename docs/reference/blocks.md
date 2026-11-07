# Blocks

Markdown content has three tiers, and most pages should live in the first two:

1. **Prose** in Markdown: headings, paragraphs, lists, pipe tables, images.
2. **Blocks** for the structured pieces: a callout, a row of figures, a
   captioned table, a dense grid bound to a data pack. Each block is declared
   by the library whose vocabulary it emits, so it renders correct markup
   every time and fails the build, at `file:line`, when it is written wrong.
3. **`::: html` islands** for anything bespoke — a custom SVG figure, an
   interaction no block covers. The body is copied verbatim.

Reach for the lowest tier that can say it. A block costs a fraction of the
markup it expands to, cannot invent a class, and keeps its numbers in the
data rather than retyped into the page. The island keeps ambition possible
without giving up the safety net: the invented-class check, `artoo verify`,
the design lint, and the browser checks all still apply to it. Use kit
classes and tokens inside it (`var(--accent)`, `var(--chart-1)`), never raw
colours or fonts.

## Syntax

```markdown
::: callout warn #caveat title="The denominator changed"
Counts before 2024 exclude **charter schools**.
:::
```

- The opening fence is three or more colons, the block name, then
  attributes in any order: `key=value`, `key="quoted value"`, `#id`, and
  bare words for flags or the block's one positional attribute.
- The body is Markdown, one item per line, or raw HTML, depending on the
  block (listed below).
- A line of the same number of colons closes it. To nest, give the outer
  block more colons: `:::: wide` … `::: callout` … `:::` … `::::`.
- An `#id` lands on the block's root element. Use it to link to the block
  and to name it when you revise: "tighten the `#caveat` callout".

Every block's root also carries `data-block` and `data-src="content.md:12"`.
That is how a browser finding ("overflows at 390px") names the line that
produced the element.

## Revising

Edit the source in place and rebuild. Do not regenerate a page to change
part of it: rewriting a whole page is where earlier fixes silently come
undone. Target the block by its `#id` or its line, change what the finding
names, and run `artoo build` again.

## Errors

A block written wrong fails the build and names the fix:

```
content.md:14: `callout` block has no attribute 'tone' (did you mean "title"?); it takes variant, title
content.md:22: unknown block "calout" (did you mean "callout"?) — `artoo docs blocks` lists the blocks this artifact can use
content.md:31: `grid` block: column field 'prof_pct' is not in the data (it has county, hhi, id, name, prof)
```

The first block that needs a library vendors it (the `grid` block adds
`artoo-grid`); after that the artifact keeps the bytes it pinned, and
`artoo lib update` stays the only upgrade boundary.

## Catalog

### `callout`

A boxed aside for a caveat, warning or result the reader must not miss.

From `artoo-kit`. Body: Markdown.

| attribute | meaning |
|---|---|
| `variant` | tone (one of `note`, `warn`, `danger`, `success`; may be written bare) |
| `title` | bold first line |

```markdown
::: callout warn title="The denominator changed"
Counts before 2024 exclude charter schools.
:::
```

### `stats`

A row of 2–6 headline figures, one `value | label` line each.

From `artoo-kit`. Body: one item per line.

```markdown
::: stats
$4.2M | spent in 2025
38% | of it on staffing
12 | vendors
:::
```

### `pullquote`

A breakout-width quotation; attribute it with cite=.

From `artoo-kit`. Body: one item per line.

| attribute | meaning |
|---|---|
| `cite` | who said it, and where |

```markdown
::: pullquote cite="Superintendent, board minutes, March 2025"
We were budgeting for a district that no longer exists.
:::
```

### `pullnumber`

One large figure with its label, breakout width.

From `artoo-kit`. Body: one item per line.

| attribute | meaning |
|---|---|
| `value` | the figure, formatted as it should read (required) |

```markdown
::: pullnumber value="1 in 7"
builds failed to launch with no checks at all
:::
```

### `figure`

Caption and source for whatever it wraps — a pipe table, an image, a grid or html block; state vintage and denominator in the caption.

From `artoo-kit`. Body: Markdown.

| attribute | meaning |
|---|---|
| `caption` | what the reader is looking at, with vintage and denominator |
| `source` | where the figures come from |

```markdown
::: figure caption="Spending by category, FY2025 (USD)" source="District ledger"
| Category | Amount |
|---|---:|
| Staffing | 1,600,000 |
:::
```

### `wide`

Let its contents run wider than the prose column (breakout width).

From `artoo-kit`. Body: Markdown.

```markdown
::: wide
| A | B | C | D | E | F |
|---|---|---|---|---|---|
| 1 | 2 | 3 | 4 | 5 | 6 |
:::
```

### `full`

Let its contents run edge to edge.

From `artoo-kit`. Body: Markdown.

```markdown
::: full
![Panorama of the site](assets/panorama.png)
:::
```

### `cards`

Navigation cards to other pages, one `[Title](page.html) — description` line each.

From `artoo-kit`. Body: one item per line.

| attribute | meaning |
|---|---|
| `label` | accessible name for the group (default: Pages) |

```markdown
::: cards
[Method](method.html) — how the figures were built
[Data](data.html) — every table, downloadable
:::
```

### `lede`

The opening paragraph, set larger.

From `artoo-kit`. Body: one item per line.

```markdown
::: lede
The district spent more on substitutes than on textbooks.
:::
```

### `grid`

A sortable dense table bound to a [[data]] pack; one `field | Title | format flags` line per column. Fields are checked against the pack at build time.

From `artoo-grid`. Body: one item per line.

| attribute | meaning |
|---|---|
| `data` | the [[data]] pack's global name (required) |
| `rows` | dotted key of the row array inside the pack, if it is not the root |
| `index` | field that identifies a row |
| `search` | show the free-text filter (flag) |
| `columns` | show the column picker (flag) |
| `download` | CSV filename for the export button |
| `note` | footer: vintage, denominator, source |
| `caption` | figure caption under the table |

```markdown
::: grid data=DISTRICTS index=id search columns download=districts.csv note="ACS 2020–2024"
name | District | name frozen sub=county
hhi | Median household income | currency bar
prof | Proficient | percent heat decimals=1
:::
```

### `html`

Raw HTML, copied verbatim — the escape hatch for a bespoke figure or interaction. Use kit classes and tokens (`var(--accent)`); the class check, verify, the design lint and the browser checks still apply.

From core. Body: raw HTML, verbatim.

```markdown
::: html #timeline
<figure class="article-figure diagram">
  <svg viewBox="0 0 320 40" role="img" aria-label="Spending rose each year"><rect class="timeline-bar" x="0" y="10" width="320" height="20"/></svg>
</figure>
:::
```
