"""artoo-controls: common explorer controls over an in-memory row set."""

from pathlib import Path

from .. import Library

VERSION = "0.1.0"
NAMESPACES = ("controls-",)

CLASSES = {
    "controls": "root enhanced by ArtooControls.create()",
    "controls-bar": "responsive row containing search, filters, and actions",
    "controls-field": "label and input pair",
    "controls-search": "free-text search input",
    "controls-select": "single- or multiple-value filter",
    "controls-actions": "reset, download, and optional preset actions",
    "controls-summary": "live result summary and active filters",
    "controls-count": "aria-live result count",
    "controls-chips": "active-filter list",
    "controls-chip": "button that removes one active filter",
    "controls-reset": "clear-all button",
    "controls-download": "CSV download button",
    "controls-save": "save-current-configuration button",
    "controls-load": "restore-saved-configuration button",
    "controls-status": "preset durability and result feedback",
    "controls-empty": "accessible empty-result message authored by the explorer",
}

library = Library(
    name="artoo-controls",
    version=VERSION,
    summary=(
        "Search, filter groups, active chips, result counts, URL state, CSV downloads, "
        "and optional saved explorer configurations."
    ),
    root=Path(__file__).parent / "assets",
    namespaces=NAMESPACES,
    classes=CLASSES,
)
