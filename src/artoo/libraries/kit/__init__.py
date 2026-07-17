"""artoo-kit: the built-in site library.

DES-governed, self-contained styling for public artifacts: a light editorial
default, an explicit dark opt-in, long-form article layout, evidence regions,
and a small component vocabulary. System font stacks only — a page using the
kit renders from file:// with zero external requests.
"""

from pathlib import Path

from .. import Library

VERSION = "0.2.0"

library = Library(
    name="artoo-kit",
    version=VERSION,
    root=Path(__file__).parent / "assets",
)
