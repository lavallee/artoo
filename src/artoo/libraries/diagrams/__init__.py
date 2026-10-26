"""artoo-diagrams: Mermaid-syntax diagrams, rendered offline by Pele.

Authors write Mermaid; the renderer is an implementation detail behind this
library's name. Today it is `Pele <https://pele.run>`_: synchronous, no
runtime dependencies, a quarter of mermaid.js's weight, and themed through CSS
variables — so a diagram follows the kit's light/dark toggle without being
redrawn. Naming the library for its role rather than its engine is deliberate:
Pele is young and fast-moving, and an artifact's contract should survive a
renderer swap.

``pele.global.js`` is upstream's browser bundle, byte for byte, refreshed only
by ``scripts/update-pele.py``, which checks the npm integrity hash and the
release's build provenance and records both in ``pele.json``. The library
version is ``<pele version>+artoo.<REVISION>``: the first half says which
Pele an artifact carries, the second moves when artoo's own glue changes.
"""

import json
from pathlib import Path

from .. import Library

_HERE = Path(__file__).parent

UPSTREAM = json.loads((_HERE / "pele.json").read_text(encoding="utf-8"))
PELE_VERSION = UPSTREAM["version"]
# Bump when diagrams.js or diagrams.css change; a Pele refresh changes the
# version on its own.
REVISION = 1
VERSION = f"{PELE_VERSION}+artoo.{REVISION}"

CLASSES = {
    "mermaid": (
        "a Mermaid source block (`<pre class=\"mermaid\">`); diagrams.js replaces it with "
        "the rendered diagram, themed from the kit's tokens"
    ),
}

library = Library(
    name="artoo-diagrams",
    version=VERSION,
    summary=(
        f"Mermaid-syntax diagrams rendered offline by Pele {PELE_VERSION}: flowcharts, "
        "sequences, state, ER, timelines, and more, following the page's theme."
    ),
    root=_HERE / "assets",
    classes=CLASSES,
)
