# Code maps

Artoo code maps are evidence-bearing graphs for interrogating a repository. The
product is not one giant architecture picture. It is one inspectable graph that
can answer many bounded questions: what enters here, what can it reach, what
depends on this, why is this relationship shown, and which facts changed.

## Build the graph

```bash
artoo map build .
# → .artoo/codegraph.json

artoo map build . --out work/codegraph.generated.json --exclude site/explainer/
```

The built-in analyzer is deliberately conservative and currently Python-first.
It parses packages, modules, public and private definitions, local imports,
resolvable local calls, declared project dependencies, and `[project.scripts]`
entry points. Syntax failures and unsupported source languages are preserved in
`snapshot.coverage`; they are never silently treated as an empty graph.

Artoo core makes no model calls. External analyzers can write the same contract
and use every interrogation and rendering surface without becoming an Artoo
dependency:

```bash
artoo map schema > codegraph-v1.json
artoo map view their-graph.json --format mermaid
```

The schema is also published at
`https://lavallee.github.io/artoo/schema/codegraph-v1.json`.

## Four kinds of truth

Every node and relationship carries one truth class:

| class | what it establishes | what it does not establish |
|---|---|---|
| `declared` | intended or configured architecture | implementation or runtime conformance |
| `static` | a relationship found in one source snapshot | whether the path runs or is important |
| `runtime` | behavior observed in one named trace | whole-system absence or typicality |
| `inferred` | a proposed label, group, or relationship | observed fact |

These classes do not collapse. A renderer may filter them but cannot promote
one. A model-generated edge must remain `inferred`, even when plausible. An
unobserved runtime path is unknown, not absent.

## Ask bounded questions

```bash
# A saved overview as renderer-neutral JSON.
artoo map view .artoo/codegraph.json --view overview --budget 80

# Focus on one definition and walk outward two hops.
artoo map view .artoo/codegraph.json \
  --focus artoo.cli.main --direction outgoing --depth 2 --format mermaid

# Inspect the reason and source receipt for a node and its adjacent edges.
artoo map why .artoo/codegraph.json artoo.cli.main

# Find a shortest directed evidence path.
artoo map path .artoo/codegraph.json entrypoint:artoo artoo.cli.main

# Select question-relevant source coordinates under an approximate token budget.
artoo map context .artoo/codegraph.json \
  "where does deploy enter and what can it call?" --budget-tokens 800
```

References resolve from a stable id, repository-relative path, qualified name,
or unique label. An ambiguous name is refused and the error prints candidate
stable ids. `view`, `why`, `path`, and `context` all accept machine-readable
JSON where useful.

The context rank is transparent: query matches, declared entry points, public
definitions, and typed graph degree determine the order. Its token count is an
estimate of one token per four characters. Ranking is navigation help, not a
claim that the highest-scoring code is the most important architecture.

## The contract

`artoo-codegraph/1` has five main parts:

| part | role |
|---|---|
| `snapshot` | repository revision, dirty state, analyzers, coverage, exclusions, truncation |
| `nodes[]` | stable id, kind, label, optional source coordinate, parent, truth, attributes |
| `edges[]` | typed endpoints, truth, confidence, reason, and one or more evidence coordinates |
| `traces[]` | optional named runtime records and their vintage/coverage receipts |
| `views[]` | question, direction, depth, budget, layers, and optional relationship kinds |

Paths must be repository-relative. Absolute local roots are rejected so a
published graph does not leak a workstation path. A dirty snapshot withholds
its remote `source_base`: the local line might not exist at the recorded commit,
so printing the coordinate is more honest than linking to different code.

## Interactive artifacts

`artoo generate explainer` writes:

```text
work/codegraph.generated.json   private retained graph and agent context source
site/data/codegraph.json        publishable renderer-neutral graph
site/data/codegraph.js          identical file://-safe browser global
site/code-map.html              interactive bounded views and receipts
site/lib/artoo-map/             versioned, hash-pinned viewer assets
```

The Code map page supports saved overview/call views, focus, direction and depth,
directed paths, truth-layer toggles, node and edge evidence, URL state, and JSON,
Mermaid, and static SVG exports. Its canvas has an ordinary keyboard-navigable
node table beneath it. The initial layout is breadth-first and stops moving; it
is not a force-directed hairball.

`artoo-map` is a renderer, not an analyzer. Its API and class vocabulary are in
`artoo docs artoo-map`.

## Ownership and extension boundary

Artoo core owns the contract, validation, bounded queries, evidence receipts,
and renderer-neutral projections. The explainer owns optional agent narrative
and uses `artoo map context` semantics to rank where each area analysis begins.
Site libraries own only presentation. External language analyzers and runtime
recorders own their extraction cost and coverage.

This stays inside Artoo during 0.x because it shares artifact custody, vendoring,
verification, documentation, and the publish firewall. A parser or renderer
should become another distribution only after its dependency weight, release
cadence, or independent consumers create a real operational boundary.
