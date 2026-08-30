# Generators

A generator produces an artifact's content programmatically. They are plugins,
resolved from the `artoo.generators` entry-point group, so a repo can ship its
own without patching artoo.

```bash
artoo generate                       # list what is installed
artoo generate <name> --help         # a generator's own options
```

## Models stay outside artoo

artoo core makes no model calls and holds no API keys. Model-powered
generators delegate to **agent CLIs already on your PATH** — `claude`,
`codex` — configured per artifact:

```toml
[workers]
cheap = "codex"      # fan-out: per-module analysis, inventory passes
strong = "claude"    # synthesis: the narrative, the argument
```

The split is deliberate: fan-out work is wide and shallow, synthesis is narrow
and deep, and paying strong-tier rates for the first is waste.

## Built in

### `explainer` — a repo explainer

```bash
artoo generate explainer --repo . --out site/explainer
```

Inventories the repo deterministically, builds an evidence-bearing
`artoo-codegraph/1`, fans per-module analysis out to the cheap worker,
synthesizes the narrative with the strong worker, renders architecture
diagrams, and assembles a multi-page site with the kit. Graph ranking gives
each area worker a bounded set of source coordinates to inspect first; the
ranking is navigation help, not architectural authority. Planning starts from
a named reader decision, a supportable headline claim, a
counter-reading, and the licit comparisons — *before* it picks tables or
figures. The output is a dated snapshot with a colophon recording exactly how
it was made.

Every explainer also includes an offline Code map page: saved bounded views,
focus, paths, declared/static/runtime/inferred toggles, and source receipts over
the same graph the workers used. See `artoo docs code-maps`.

### `notebook-report` — a report from a notebook

```bash
artoo generate notebook-report --notebook path/to/notebook --out site/report
```

The read half of the flip roundtrip. See `artoo docs provenance`.

## Writing one

Export a callable and register it:

```toml
[project.entry-points."artoo.generators"]
my-generator = "mypkg.gen:generate"
```

Generators that write into `site/` should use the vendored library vocabulary —
`artoo docs artoo-kit` — so their output passes the same markup check as
hand-authored pages.
