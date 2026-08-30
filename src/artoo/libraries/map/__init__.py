"""artoo-map: interactive projections over an artoo-codegraph/1 document."""

from pathlib import Path

from .. import Library

VERSION = "0.1.0"
NAMESPACES = ("map-",)

CLASSES = {
    "map": "interactive code-map root enhanced by ArtooMap.create()",
    "map-toolbar": "wrapping controls for views, focus, layers, paths, and exports",
    "map-field": "label and input pair inside the toolbar",
    "map-search": "node focus or path endpoint input",
    "map-select": "saved-view, direction, or depth selector",
    "map-layers": "truth-layer checkbox group",
    "map-layer": "one declared, static, runtime, or inferred layer toggle",
    "map-actions": "map reset and export action group",
    "map-button": "button used for actions and accessible node focus",
    "map-status": "aria-live summary of the visible bounded view and coverage",
    "map-stage": "responsive graph and evidence-detail split",
    "map-canvas": "Cytoscape canvas container",
    "map-detail": "selected node or edge evidence inspector",
    "map-detail-title": "heading inside the evidence inspector",
    "map-detail-meta": "kind, truth, confidence, and relationship metadata",
    "map-evidence": "list of source coordinates supporting the selection",
    "map-coordinate": "one source coordinate, optionally linked to the pinned revision",
    "map-truth": "truth-class badge",
    "map-fallback": "keyboard-navigable table alternative to the graph canvas",
    "map-table": "node table inside the accessible fallback",
    "map-empty": "message shown when filters remove every node",
}

library = Library(
    name="artoo-map",
    version=VERSION,
    summary=(
        "Interactive evidence-bearing code maps: saved views, focus, paths, truth layers, "
        "source receipts, and JSON, Mermaid, and SVG exports."
    ),
    root=Path(__file__).parent / "assets",
    namespaces=NAMESPACES,
    classes=CLASSES,
)
