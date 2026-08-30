# artoo-map

An interactive projection of an `artoo-codegraph/1` document. The library does
not analyze code and does not decide what the architecture is. It renders the
truth class and evidence receipt that each node or relationship already carries.

Vendored into an artifact at `site/lib/artoo-map/` with a pinned hash;
`artoo lib update artoo-map` is the explicit upgrade boundary.

| file | role |
|---|---|
| `cytoscape.min.js` | vendored Cytoscape.js 3.34.0 graph renderer (MIT) |
| `map.js` | bounded views, focus, directed paths, receipts, and exports |
| `map.css` | restrained Artoo UI over the canvas and accessible fallback |
| `CYTOSCAPE-LICENSE` | upstream MIT license text |

## Loading a map

The graph can be loaded from a JavaScript global, so the artifact still works
from `file://` without a fetch or local server:

```html
<link rel="stylesheet" href="lib/artoo-map/map.css">
<div id="code-map" class="map" aria-label="Interactive code map"></div>
<script src="lib/artoo-map/cytoscape.min.js"></script>
<script src="data/codegraph.js"></script>
<script src="lib/artoo-map/map.js"></script>
<script>
ArtooMap.create("#code-map", {
  graph: window.ARTOO_CODEGRAPH,
  view: "overview",
  budget: 120,
});
</script>
```

`artoo generate explainer` writes and wires these files automatically. For a
hand-authored artifact, generate the graph with `artoo map build`, put the same
JSON object on `window.ARTOO_CODEGRAPH`, and vendor this library.

## What the reader can ask

- switch a saved view;
- focus on one path, symbol, package, entry point, or external dependency;
- traverse incoming, outgoing, or both directions at a bounded depth;
- find a shortest directed path between two nodes;
- toggle declared, static, runtime, and inferred truth layers independently;
- select any node or edge to see its reason and source coordinates;
- export the current bounded view as JSON, Mermaid, or a static SVG;
- use the node table instead of the canvas with a keyboard or screen reader.

The opening layout is breadth-first and stops moving after it is computed. It
does not use a live force simulation. A bounded view is the product; a repository
hairball is not.

## Truth is not blended

The four layers mean different things:

| layer | establishes |
|---|---|
| `declared` | intended or configured architecture |
| `static` | a relationship found in the source snapshot |
| `runtime` | behavior observed in one named trace |
| `inferred` | a proposed label, group, or relationship |

Turning a layer off hides it. Turning one on does not promote it. An inferred
edge stays visibly inferred; a runtime edge does not imply unrecorded paths are
absent.

## Source links and dirty worktrees

`snapshot.source_base` may name a pinned repository URL. Artoo omits it for a
dirty worktree because the local coordinate may not exist at the recorded
commit. The inspector still prints the path and line, while the status names
the dirty snapshot rather than linking to misleading source.

## Licence

Cytoscape.js is MIT-licensed, © 2016-2026 The Cytoscape Consortium. The vendored
license is in `CYTOSCAPE-LICENSE`. Artoo's wrapper and styles are MIT-licensed
with the rest of Artoo.
