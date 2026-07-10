"""artoo-kit: the built-in site library.

Neutral, self-contained styling for generated artifacts: design tokens
(dark default, light theme), base styles, an article layout with margin
notes, and a small component vocabulary. System font stacks only — a page
using the kit renders from file:// with zero external requests.
"""

from pathlib import Path

from .. import Library

VERSION = "0.1.0"

library = Library(
    name="artoo-kit",
    version=VERSION,
    root=Path(__file__).parent / "assets",
)
