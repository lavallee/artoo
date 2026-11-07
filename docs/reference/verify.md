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

## Optional browser proof

```bash
artoo verify path/to/artifact --browser
artoo verify path/to/artifact --browser --screenshots work/verification
```

Browser verification is a soft Playwright integration. When requested, it
firewall-stages the site, opens every publishable page in Chromium at phone and
desktop widths, reports page and console errors, checks horizontal overflow,
and optionally records full-page screenshots. Core Artoo does not depend on Playwright; if it is absent the
command names the install needed or lets you omit `--browser`.

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
