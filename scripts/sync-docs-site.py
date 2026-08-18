#!/usr/bin/env python3
"""Regenerate the published reference under docs/ from the installed package.

The reference has one source — artoo.docs — rendered onto three surfaces:
`artoo docs` for a shell, AGENTS.md inside each artifact, and the files this
script writes for anything reading over HTTP. Run it whenever a reference
topic or a library's class vocabulary changes; a test fails if you forget.

    uv run python scripts/sync-docs-site.py
"""

from pathlib import Path

from artoo import docs

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    written = docs.write_site(ROOT / "docs")
    for path in written:
        print(path.relative_to(ROOT))
