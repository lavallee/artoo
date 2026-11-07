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

<!-- artoo:blocks -->
