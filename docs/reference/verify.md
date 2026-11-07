# Verification

`artoo build` runs static verification after rendering content, packing data,
and projecting evidence. `artoo verify` runs it without changing the artifact.

Hard failures cover:

- missing HTML or CSS assets and internal pages;
- broken fragment anchors and duplicate IDs;
- references that escape `build.site` or target a firewall-withheld path;
- root-relative paths that fail from `file://`;
- remote scripts, styles, fonts, images, and other runtime dependencies;
- literal remote CSS imports or JavaScript fetch/import calls.

Warnings identify images without `alt`, tables without headings or with uneven
row widths, and empty or nowhere-pointing controls. They are review prompts,
not taste scores, and do not fail a build.

## Browser checks

Some faults only exist once a page is drawn: a table that pushes the page
sideways on a phone, a diagram that never rendered, text cut off by its box.
A static pass cannot see them and an author rarely looks at every page at
every width, so `artoo build` opens the pages itself.

After the static checks pass (a structurally broken site fails fast, without
a browser), the build firewall-stages the site, opens every publishable page
in Chromium at phone (390×844) and desktop (1440×900) width, and runs the
checks below in the page.

These fail the build:

- page errors and console errors, with the file and line that raised them;
- horizontal overflow, naming up to three boxes that cause it: the widest
  ones whose right edge passes the viewport, skipping anything inside a
  scroll or clip container and anything inside a box already named;
- broken images: loaded, but not decodable as an image;
- Mermaid diagrams that did not render: a `pre.mermaid` block (or its
  rendered host) with no `<svg>` after a few seconds. A diagram whose source
  failed to parse is reported once, through its console error.

These are warnings, review prompts that do not fail the build:

- clipped text: text cut at the edge of a box with `overflow: hidden` or
  `clip`. Scroll containers, `text-overflow: ellipsis`, line clamps, the
  sr-only pattern and text staged wholly outside its box (an inactive slide)
  are deliberate and skipped;
- small text: visible text under 10.5px. Real artifacts use 11px labels and
  10.8px code in a colophon on purpose; the line is drawn below them;
- contrast under WCAG AA: 4.5:1, or 3:1 for large text (24px, or 18.66px
  bold), against the background composited from the element's ancestors. A
  background image, gradient, blend or positioned box in the way makes the
  background unknown, and unknown is skipped, never guessed. Ornament
  characters such as `·` are not judged;
- overlap: text in an absolutely positioned box whose glyphs land on other
  text. Fixed and sticky chrome floats over content by design and is left out.

Each finding names the page, the viewport, a short selector, the nearest
heading with an id (`§methods`) and, where the page records one, the source
line it came from (`content.md:42`). A rule reports at most three findings per
page and viewport, then "and N more"; a finding seen at both widths is one
line naming both.

### The contact sheet

The build writes a screenshot of every page at both widths to
`work/verification/` and composes them into one image,
`work/verification/contact-sheet.png`, which the build prints as
`look once: …`. Look at it once, after the checks pass: it is the cheapest
way to see the whole artifact the way a reader will, and a better use of a
review than another polishing loop. `work/` never publishes.

### When it runs

`[verify] browser` in `artifact.toml` sets the policy:

- `auto` (the default) runs the checks where Playwright and Chromium are
  installed. Elsewhere the build prints one note line and carries on.
- `always` makes their absence a build failure, for a machine or CI job that
  is meant to prove the pages render.
- `never` skips them.

`artoo build --browser` or `--no-browser` overrides the manifest for one run.
Playwright is a soft dependency that core artoo never requires. To install it
beside a `uv tool` install:

```bash
uv tool install artoo-artifacts --with-executables-from playwright
playwright install chromium
```

`artoo verify` stays static unless asked:

```bash
artoo verify path/to/artifact --browser
artoo verify path/to/artifact --browser --screenshots work/verification
```

`--browser` runs the same checks; `--screenshots DIR` also writes the
per-page screenshots and the contact sheet there.

A clean check proves structural and runtime integrity. It does not promote an
artifact's status or establish factual, editorial, visual, or human acceptance.

## Design lint

A page can pass every integrity check and still read as generated: gradient
headline text, frosted-glass panels, an emoji in front of every heading, "01 /
02" eyebrows, cards that hold content instead of linking anywhere, colours and
fonts typed in by hand instead of taken from the kit, stock model prose. Those
habits are easier to name than to notice, so artoo names them. Each rule below
is deterministic — no model call, no score — and carries its fix in kit
vocabulary.

`artoo build` and `artoo verify` run the lint over the artifact's own
publishable HTML and CSS, including inline `style=` attributes and `<style>`
blocks. Vendored libraries under `site/lib/` are never linted: their CSS is
where the tokens are defined. Findings are **warnings** — printed, and listed
under `"warnings"` in `--json` output — and never fail a build. Each names the
file, line, and rule:

```text
site/index.html:42 [raw-color] color: #1f2430 — use a kit token — var(--text), …
```

A rule reports at most three hits per file and five files per artifact, then
counts the rest, so one shared inline `<style>` across a generated site says
it once.

| rule | what it catches | fix |
|---|---|---|
| `raw-color` | a hex, rgb(), or hsl() colour typed into page CSS or a style= attribute | use a kit token — var(--text), var(--muted), var(--accent), var(--surface), var(--border), var(--chart-1)…var(--chart-8) — or define your own once as a custom property (--brand: #…) and use var(--brand) |
| `foreign-font` | a font-family that names a web font, or sets a family without a kit font token | use var(--font-prose), var(--font-ui), var(--font-display), or var(--font-numeric); the kit stacks are offline system fonts |
| `gradient-text` | text painted with a gradient via background-clip: text | give the text a solid colour such as var(--text) or var(--accent); let size and weight carry the emphasis |
| `glass` | a frosted-glass panel: backdrop-filter with blur() | use an opaque surface: background: var(--surface); border: 1px solid var(--border) |
| `emoji-icon` | a heading, list item, button, or nav link whose text starts with an emoji | drop the emoji and let the words lead; if an icon earns its place, use an inline SVG with aria-hidden="true" |
| `numbered-eyebrow` | a counter used as decoration: an element that is only "01" / "02 —", or a heading that starts "01." | drop the counter and name the section; if order matters, use an &lt;ol> (or class="toc" for contents) |
| `card-as-container` | a nav-card (or card) that is not a link and holds no link | nav-card is for links to destinations: make it &lt;a class="nav-card" href=…>, or use a plain &lt;section> or class="callout" for content |
| `stock-copy` | a stock phrase of generated prose ("delve", "seamless integration", "unlock the power", "it's not just X, it's Y" …) | say the specific thing in plain words: what it does, for whom, by how much |

Two choices keep the rules quiet on good work. Defining a token is the right
pattern, so a colour inside a custom-property definition (`--brand: #0b5`)
passes, as does any `var(--x)` and the fallback inside it; only a literal at a
usage site is reported. Likewise any `font-family: var(--…)` passes, and a
web font is caught where it is first named. A plain `.card` is only a
finding on pages that load artoo-kit, where it is the deprecated alias of
`nav-card`; elsewhere it is the page's own class. A blurred backdrop on a
sticky or fixed bar, a near-opaque surface, or a dialog's `::backdrop` is a
legibility device, not glass. Check marks, arrows, and stars (✓ → ★) are
typography; the emoji rule covers pictographs and anything written with the
emoji selector (⚠️).

An artifact that breaks a rule on purpose — its own design system with
literal colours, say — says so in the manifest, where the exception stays
visible:

```toml
[verify]
allow = ["raw-color", "foreign-font"]
```

An id in `allow` that is not a rule is a build problem that lists the real
ones, because a typo there would silently allow nothing.
