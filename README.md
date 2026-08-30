# artoo

**Generate and manage artifacts** — self-contained HTML mini-sites that pair
presentation with the research backing it.

There's a burgeoning practice of getting explanations of systems out of LLMs
as real pages — with navigation, diagrams, and provenance — instead of
markdown dumps, and of composing reports from multiple assets. artoo is the
tool layer for that practice:

- **Artifacts live anywhere.** An artifact is a directory with an
  `artifact.toml` inside whatever repo owns it. A library's explainer lives
  in that library's repo. One repo can hold many artifacts.
- **Self-contained, with provenance.** The publishable `site/` renders from
  a `file://` URL — vendored assets, no bundler, no CDN dependencies. Shared
  components come from versioned, hash-pinned site libraries you can upgrade
  deliberately.
- **Deployment-aware.** artoo understands GitHub Pages (including whether
  your repo serves from `/docs`, a workflow, or a branch), ssh/rsync targets,
  and arbitrary publish commands. Secrets never enter the repo.
- **Research stays with the piece.** Notebooks, working files, and anything
  `_`-prefixed sit next to the presentation but can never ship — the deploy
  path is deny-by-default.
- **Generators, not API keys.** Model-powered generators (like the repo
  explainer) delegate to agent CLIs you already have — `claude`, `codex` —
  with cheap tiers for fan-out analysis and strong tiers for synthesis.
  artoo core makes no model calls and holds no keys.
- **Code maps are questions, not hairballs.** A versioned graph keeps declared,
  static, runtime, and inferred relationships separate, then produces bounded
  views for focus, paths, source receipts, and agent context.
- **Artoo owns its artifact contract.** New work starts with an explicit reader
  decision, evidence limits, valid comparisons, and a chosen presentation form.
  Its accessible kit is a foundation, not a visual authority.
- **The contract travels with the work.** `artoo init` writes a concise
  `AGENTS.md` and an on-demand `ARTOO_REFERENCE.md` carrying the class vocabulary
  its vendored library defines, `artoo docs` answers the same questions, and
  `artoo build` reports a class that vocabulary does not contain. Authoring
  an artifact should never mean reverse-engineering one.

## Install

```bash
uv tool install artoo-artifacts   # or: pipx install artoo-artifacts
artoo --version                   # the command is `artoo`
```

Research-notebook support activates automatically when
[flip](https://github.com/lavallee/flip) is installed alongside artoo — both
the write half (generator runs recorded as sources/claims/sessions) and the
read half (below). artoo discovers flip on `PATH`; pin a specific build with
`ARTOO_FLIP_BIN`. With no flip installed, artoo core works unchanged.

## Quickstart

```bash
# Scaffold an artifact inside any repo
artoo init site/my-report --kind report --form article --title "Q3 systems report"

# See every artifact in the repo
artoo list

# Check health: manifest, firewall, markup, links, assets, library drift
artoo status site/my-report
artoo verify site/my-report --browser

# Read the contract: topics, or one library's full class vocabulary
artoo docs
artoo docs artoo-kit

# Build and interrogate a renderer-neutral repository graph
artoo map build .
artoo map context .artoo/codegraph.json "where does deploy enter?"

# Publish (adapter chosen by the manifest's [deploy] table)
artoo deploy site/my-report
```

`artoo init` also creates `work/artifact-brief.md`, a private authoring contract
for the reader decision, headline claim, evidence boundaries, data vintages,
licit comparisons, presentation intent, and proof required. It never enters
the deployable `site/` tree.

## Authoring without guesswork

An artifact is usually built by whoever owns its subject, from inside their
repo — increasingly an agent rather than a person. That reader has the
artifact directory and nothing else, so the contract ships with it:

```bash
artoo init docs/spending --title "Where the money went"
#   contract  AGENTS.md — concise working rules
#   reference ARTOO_REFERENCE.md — full vocabulary, on demand
```

`AGENTS.md` keeps automatic context small. `ARTOO_REFERENCE.md` carries the
full table of every class the vendored libraries define with its role,
generated from the stylesheets *that artifact* is carrying. `artoo lib add`
and `artoo lib update` regenerate both; notes outside the managed `AGENTS.md`
block are kept.

The same reference answers from a shell, and offline:

```bash
artoo docs                     # every topic
artoo docs artoo-kit           # the full class vocabulary, with roles
artoo docs --all               # the whole contract in one read
artoo skill install            # SKILL.md + references/ for a coding agent
```

Then the loop closes at build time. A class used inside a library's namespace
that its stylesheet does not define is reported, with the nearest real class
when the mistake is a typo:

```
✗ site/index.html: class "article-ful" is in the artoo-kit `article-`
  namespace, but the vendored stylesheet defines no such class (did you mean
  "article-full"?) — `artoo docs artoo-kit` lists the vocabulary it does define
```

Your own classes are never second-guessed — only the prefixes a library
declares it owns. `status`, `build`, and `doctor` all take `--json`.

The reference is also published for readers who cannot run the CLI:
[llms.txt](https://lavallee.github.io/artoo/llms.txt) and
[llms-full.txt](https://lavallee.github.io/artoo/llms-full.txt).

## Forms

`kind` describes the subject; `form` describes how a reader uses it. The four
forms are `article`, `explorer`, `collection`, and `deck`. Articles and
collections can render conservative Markdown deterministically. Explorers get
common controls and offline data packing. Raw HTML remains the escape hatch.
See `artoo docs forms`.

## Decks

`kind = "presentation"` is a first-class output, not an article with different
styling. `artoo init --kind presentation` stamps a working deck: acts, speaker
notes, an overview grid, keyboard and touch navigation, deep-linkable slides,
and an A4-landscape print stylesheet that puts one slide on one page.

```bash
artoo init talks/q3-review --kind presentation --title "Q3 review"
```

The machinery is the built-in **`artoo-deck`** library, vendored and hash-pinned
like any other. It reads structure from the markup rather than configuration —
`data-act` groups slides in the overview, `data-short` labels them — and with
JavaScript off every slide is still in the document and the deck still prints
whole. See `src/artoo/libraries/deck/README.md` for the markup contract.

Every class it ships is prefixed `deck-`, and a test enforces that. Chrome and
content share one stylesheet, so an unprefixed chrome class captures content
using the same word: a `.bar` fixed header sets `height: 46px` on an SVG
`<rect class="bar">` and collapses a chart. Keep your own classes out of the
`deck-` namespace and the two cannot reach each other.

## Dense tables, and explorers that remember

A comparison table of a few hundred entities across a few dozen measures is a
normal output of analytical work, and hand-rolling one costs the same two days
every time. **`artoo-grid`** is that work done once, over a vendored Tabulator
build — declared, not assembled:

```js
ArtooGrid.create("#table", {
  data: rows,
  columns: [
    { field: "rank", title: "#",        format: "rank", frozen: true, width: 52 },
    { field: "name", title: "District", format: "name", frozen: true, sub: "county" },
    { field: "hhi",  title: "Median household income",
      group: "Means",       format: "currency", bar: true },
    { field: "prof", title: "Proficient",
      group: "Achievement", format: "percent",  heat: true },
  ],
  toolbar: { search: true, columns: true, download: "districts.csv" },
});
```

It remains a built-in module for now: it shares Artoo's vendoring, tokens,
verification, and release cadence. The entry-point boundary is already there
if independent consumers or releases eventually justify a separate package.

Sorting, frozen identity columns, column groups, a column picker, in-cell bars
and percentile heat, and CSV export come with it. Two rules are not negotiable,
because both failures are expensive and silent: **missing is never zero** —
`null`, `NaN` and `""` render as an em dash in every format, and a row carrying
`<field>_state === "suppressed"` says so — and **blanks sort to the bottom in
both directions**, since a district with no measurement has not scored zero and
must never top a ranking. Bar and heat domains recompute on every `setData`, so
a table that reranks on a slider rescales honestly instead of comparing today's
numbers against yesterday's maximum.

Not every explorer is a grid. New explorer forms vendor **`artoo-controls`**:
search, declared filters, chips, result counts, reset, URL state, CSV, an
accessible empty state, and optional named configurations. Manifest `[[data]]`
entries turn one canonical JSON source into publishable JSON plus a
`file://`-safe JavaScript global, replacing repeated one-off packer scripts.

An explorer is only useful the second time if the configuration that made it
useful the first time survives. `artoo serve` puts a small JSON store behind
the artifact and writes named documents into its own `state/` directory:

```bash
artoo serve site/my-explorer --open
```

```js
const presets = ArtooStore.open("presets");
await presets.save("means-heavy", weights);   // → state/presets/means-heavy.json
```

Real files, next to the work, committed with it, reviewable in a diff — and
`state/` is a sibling of `site/`, so the firewall can never publish one. The
server stages the *publishable* site, so it shows exactly what a deploy would:
a withheld file is absent rather than merely unlinked. With nothing serving,
`ArtooStore` falls back to `localStorage` and reports `durable === false`, so
the page can say so instead of implying a save that did not happen.

## Evidence-bearing code maps

`artoo map` turns a repository snapshot into a renderer-neutral,
source-anchored `artoo-codegraph/1` document. The built-in analyzer is
conservative and Python-first: packages, modules, definitions, local imports,
resolvable local calls, declared dependencies, and command entry points. Parse
failures and unsupported languages remain visible coverage receipts.

```bash
artoo map build .                         # → .artoo/codegraph.json
artoo map view .artoo/codegraph.json --format mermaid
artoo map why .artoo/codegraph.json artoo.cli.main
artoo map path .artoo/codegraph.json entrypoint:artoo artoo.cli.main
artoo map context .artoo/codegraph.json \
  "what can deploy reach?" --budget-tokens 800
```

Every relationship says whether it is `declared`, found in `static` source,
observed in a named `runtime` trace, or `inferred`; it carries a reason and one
or more source coordinates. Those labels never collapse. Missing runtime
evidence does not mean a path is absent, and a plausible model edge remains an
inference.

The same graph now gives every generated explainer an offline **Code map** page:
saved bounded views, search/focus, incoming and outgoing neighborhoods, directed
paths, truth-layer toggles, evidence inspection, URL state, and JSON, Mermaid,
and SVG exports. A keyboard-navigable node table sits beneath the Cytoscape.js
canvas. The graph also ranks source coordinates for each explainer worker under
a fixed context budget, so interrogation and presentation do not become two
unrelated pipelines.

`artoo-map` remains a built-in site library during 0.x. It shares Artoo's graph
contract, offline vendoring, source receipts, verification, and publish
firewall; external language analyzers can emit the published JSON Schema
without becoming core dependencies. See `artoo docs code-maps` and
`artoo docs artoo-map`.

## Evidence and provenance roundtrip

Provider-neutral evidence can be declared directly:

```toml
[evidence]
source = "work/evidence.json"  # artoo-evidence/1
```

Artoo validates source and claim joins and projects them into the kit's
provenance panel. Flip is one optional adapter to the same browser-facing
contract, not the only route.

When an artifact declares an attached notebook (`[research] notebook = "…"`),
artoo reads it back out at build time:

```bash
artoo provenance site/my-report   # flip export json → site/data/provenance.json
artoo status site/my-report       # ... and reports if the render is stale
```

`artoo build` refreshes `site/data/provenance.json` (flip's policy-filtered
`flip-render/1` projection) and records the notebook `uid`+`updated` in
`artifact.toml` as the render vintage. The artoo-kit **provenance panel**
renders that data — sources with grades, claims with status and
verification-method badges, counts, and the notebook vintage — and turns
bracketed flip ids (`[C7]`) in prose into stable anchors that link to their
panel entry. `artoo deploy` runs `flip doctor` on the notebook first and blocks
on ERROR-level findings (`--allow-doctor-errors` overrides). The projection is
filtered by flip itself; artoo only passes `--include-private` when the manifest
sets `[research] include_private = true`. All of it no-ops cleanly without flip.

### The structural verbs

Two verbs make the loop bidirectional:

```bash
# Read direction: render a report FROM a canonical flip notebook.
artoo generate notebook-report --notebook path/to/notebook --out site/report

# Reverse direction: route a correction back INTO the notebook (never edits site/).
artoo feedback site/report "C7 overstates the effect" --claim C7
```

`generate notebook-report` is fully deterministic (no model calls). It renders
the notebook's current draft (`drafts/current`, else newest `drafts/vN`) to HTML,
or — with no draft — an honest structured skeleton (questions, claims by status,
sources by grade). The notebook is canonical; re-running regenerates the page in
place, so **edits belong in the notebook, not the render** (the colophon says so).
`--include-private` renders a non-public notebook in full.

`artoo feedback` never touches `site/`: it opens a flip question (default) or a
`flip log` event (`--as-log`) in the attached notebook, carrying the artifact ref
and any cited id. A cited `--claim`/`--source` id is verified against the notebook
and refused if unknown (typo protection); a private breadcrumb is recorded in
`work/feedback.jsonl`.

## Deprecated optional Vizier recipe

`artoo vizier-guide` remains as a deprecated compatibility recipe for artifacts
that already use [Vizier](https://github.com/lavallee/vizier). It is not part
of Artoo's authoring contract or required workflow:

```bash
artoo vizier-guide \
  "compare district spending over time without hiding enrollment change" \
  --context "Headline, caption, source, and implementation constraints" \
  --family "Change over time" --series-count 4 \
  --form-count 3 --prior-count 5 --no-semantic \
  --artifact site/my-report
```

The receipt is `work/vizier-guidance.md`. Artoo shells out to the installed CLI;
Vizier is not an Artoo dependency, and this path makes no direct model or API
call.

A clean `artoo build` proves build-command and artifact/firewall integrity. It
does not prove factual, visual, editorial, or human acceptance; review the
rendered artifact against its artifact brief before publishing.

## Generate a repo explainer

```bash
artoo generate explainer --repo . --out site/explainer
artoo deploy site/explainer
```

The explainer inventories the repo deterministically, builds the source-anchored
code graph and interactive map, fans out per-module analysis to a cheap worker
(`codex`), synthesizes the narrative with a strong worker (`claude`), renders
architecture diagrams, and assembles a multi-page site with the built-in design
kit. Planning starts from a named reader decision,
supportable headline claim, counter-reading, and licit comparisons before it
selects tables or figures. The result is a dated snapshot with a colophon saying
exactly how it was made.

## Status

v0.6.0 — alpha. The manifest format, CLI surface, and plugin entry points
are young and may change before 1.0. See [DESIGN.md](DESIGN.md) for the
architecture and [CHANGELOG.md](CHANGELOG.md) for history.

## Development

```bash
git clone https://github.com/lavallee/artoo && cd artoo
uv sync
uv run pytest -q
uv run ruff check src tests
```

MIT licensed. Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
