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
