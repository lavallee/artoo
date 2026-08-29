"""artoo-grid: dense comparison tables, declared rather than assembled.

A table of a few hundred entities across a few dozen measures is a normal
output of analytical work, and every artifact that needs one otherwise pays
the same two days for sorting, sticky identity columns, a column picker,
aligned number formats, an export, and a missing-value convention. This
library is that work done once, over a vendored Tabulator build.

The editorial rules live in the formats, which is the reason to have formats
at all rather than a `formatter` callback per column: `percent` knows whether
it was handed 0-100 or a fraction, `delta` colours by *meaning* (an `invert`
column where a rising rank is a falling district), and every format renders
null, undefined and NaN as an em dash in the missing style. That last one is
not configurable — a grid that lets a caller print 0 for a value nobody
measured will eventually do it by accident, and a zero that should have been
a blank is the most expensive kind of wrong number in a ranking.

Sorting puts blanks at the bottom in both directions for the same reason: a
district with no measurement has not scored zero and must never top a
ranking by ascending sort.

Like `artoo-deck`, this library reads structure from what it is given and
owns one class prefix, `grid-`. Tabulator's own `tabulator-*` classes are
restyled here against the artoo-kit tokens but are never part of the contract
an author writes against.
"""

from pathlib import Path

from .. import Library

VERSION = "0.1.0"

# Everything this library defines is prefixed `grid-`, so an artifact's own
# `.grid-of-cards` would be flagged. That is the intended trade: the prefix is
# short because these tables are dense and the markup is read a lot.
NAMESPACES = ("grid-",)

CLASSES = {
    "grid": "the grid root; ArtooGrid.create() adds it and fills the element",
    "grid-toolbar": "row above the table holding the count, filter, column picker, and export",
    "grid-count": "live row count; reads 'n of N rows' whenever a filter is active",
    "grid-search": "the free-text filter input",
    "grid-btn": "toolbar button",
    "grid-picker": "column-picker wrapper (button plus popover)",
    "grid-picker-menu": "the popover listing hideable columns; frozen columns are omitted",
    "grid-picker-group": "a column-group heading inside the picker",
    "grid-body": "the element Tabulator mounts into",
    "grid-note": "footer strip for vintage, denominator, and source",
    "grid-num": "tabular right-aligned figures",
    "grid-name": "primary row label",
    "grid-sub": "smaller secondary label under a name, from a column's `sub` field",
    "grid-rank": "bold ordinal",
    "grid-bar": "numeric cell with a proportional background bar; `--grid-fill` is the width",
    "grid-heat": "numeric cell tinted by percentile; `--grid-alpha` is the strength",
    "grid-delta": "signed change, coloured by direction via `data-sign`",
    "grid-chip": "short categorical label in a pill",
    "grid-missing": "the em-dash rendering of an unmeasured or suppressed value",
    "grid-nil": "muted text for a deliberately empty cell",
    "grid-row-pinned": "row held at the top of the table for comparison",
}

library = Library(
    name="artoo-grid",
    version=VERSION,
    summary="Declarative dense data tables: sorting, frozen identity columns, in-cell bars and heat, column picker, CSV export, and an honest missing-value convention.",
    root=Path(__file__).parent / "assets",
    namespaces=NAMESPACES,
    classes=CLASSES,
    vendored=("tabulator.min.css",),
)
