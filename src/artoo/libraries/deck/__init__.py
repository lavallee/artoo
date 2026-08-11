"""artoo-deck: slide machinery for presentation artifacts.

A deck is a different reading mode from an article, not a variant of one:
one frame at a time, an act structure, speaker notes, and a landscape page
when printed. This library supplies that machinery so a presentation
artifact is authored as content rather than rebuilt as chrome each time.

Every class is prefixed ``deck-``. That prefix is load-bearing: chrome and
content share one stylesheet, and an unprefixed chrome class will silently
capture a content element using the same word.
"""

from pathlib import Path

from .. import Library

VERSION = "0.1.0"

library = Library(
    name="artoo-deck",
    version=VERSION,
    root=Path(__file__).parent / "assets",
)
