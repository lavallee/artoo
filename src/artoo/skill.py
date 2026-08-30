"""``artoo skill``: install artoo's contract as an agent skill.

``AGENTS.md`` teaches an agent that is already standing in an artifact. It
cannot teach one that has been asked for "a report on X" and does not know
artoo exists — that agent hand-rolls HTML, or copies a previous artifact,
because nothing ever told it there was a tool for this.

A skill closes that gap. It advertises itself in about a hundred tokens, and
the body is only read when a task matches. The layout here is the common one:
``SKILL.md`` with YAML frontmatter, and a ``references/`` directory the agent
opens on demand rather than up front.

The skill's references are generated from :mod:`artoo.docs`, the same source
as ``artoo docs`` and the artifact's on-demand reference. A skill that drifts
from the tool it describes is worse than none.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import __version__, docs

SKILL_NAME = "artoo"

# The advertisement. It is injected into an agent's prompt for every task, so
# it has to be short, and it has to name the triggers — the words someone uses
# when they want an artifact without knowing artoo is what makes one.
DESCRIPTION = (
    "Build a self-contained HTML artifact with artoo — a report, explainer, "
    "research review, explorer, collection, or presentation deck that renders from a "
    "file:// URL with vendored styling and optional research provenance. Use "
    "when asked to produce a report, explainer, deck, one-off site, or "
    "publishable write-up inside a repo, when a directory holds an "
    "artifact.toml, or when an `artoo` command needs running. Covers init, "
    "build, deploy, the layout class vocabulary, and the deploy firewall."
)

BODY = """\
# artoo

artoo builds **artifacts**: self-contained HTML mini-sites that pair a piece of
presentation with the research behind it. An artifact is a directory holding an
`artifact.toml`, living inside whatever repo owns its subject.

Reach for it whenever the deliverable is a page rather than a markdown file: a
report, an explainer, a research review, a walkthrough, an explorer, a
collection, or a slide deck. Start from a declared Artoo form rather than
copying a previous artifact; raw HTML remains available when the form needs it.

## Check it is there

```bash
artoo --version
```

If that fails, artoo is not installed here — say so rather than approximating
it by hand. (`uv tool install artoo-artifacts`, if installing is wanted.)

## The path

```bash
artoo init docs/spending-report --kind report --form article --title "Where the money went"
```

That writes the manifest, Markdown source, vendored styling, a private artifact
brief, concise `AGENTS.md`, and an on-demand `ARTOO_REFERENCE.md`. Read the
short guide first. Open the reference only when the full class vocabulary or
firewall detail is useful.

Then author the `[content]` source named by `artifact.toml`, and:

```bash
artoo build  docs/spending-report    # verify, refresh inputs, stamp `updated`
artoo verify docs/spending-report    # links, assets, anchors, offline runtime
artoo deploy docs/spending-report    # firewall-staged publish
```

`artoo build` is the check that matters. It fails on a class used inside a
library's namespace that the library does not define, and names the nearest
real class. If it fails that way, fix the class — do not add CSS to make the
invented name work.

Kind describes the subject; form describes the reading mode:

```bash
artoo init talks/q3 --kind presentation --title "Q3 review"
artoo init data/places --kind report --form explorer --title "Compare places"
```

Kinds: `explainer`, `report`, `reference-guide`, `research-review`,
`walkthrough`, `presentation`, `case-study`, `explorer`, `note`.

Forms: `article`, `explorer`, `collection`, `deck`. Articles and collections
render deterministic Markdown. Explorers arrive with common controls and
offline JSON packing. Delete `[content]` only when taking ownership of raw
`site/` HTML deliberately.

## Rules that are not negotiable

1. **Use the vendored vocabulary.** `ARTOO_REFERENCE.md` and
   `artoo docs artoo-kit` list every class with its role. An
   invented class renders as nothing and reads as a styling bug.
2. **Nothing loads from the network.** The page must render from `file://` —
   no CDN scripts, no remote fonts, no external stylesheets. Vendor a runtime
   with `artoo lib vendor <name> <url>`; it is recorded with a pinned hash.
3. **Style SVG with CSS, not presentation attributes.** `fill="var(--chart-1)"`
   does not resolve. Give the shape a class and set `fill` in a `<style>`
   block — that also lets the chart follow the theme.
4. **Research never lands in `site/`.** Put it in `work/` or an attached
   notebook. Publishing is deny-by-default; see the firewall reference.

## Finding your way

```bash
artoo docs                  # every topic
artoo docs <topic>          # one topic in full
artoo docs --all            # the whole contract in one read
artoo list .                # artifacts in this repo (--json for machines)
artoo doctor .              # repo-wide coherence check
```

The `references/` directory beside this file holds the same topics offline.
Read `references/quickstart.md` first, then the library reference for whatever
the artifact vendored.
"""


@dataclass(frozen=True)
class Installed:
    root: Path
    files: list[Path]


def skill_markdown() -> str:
    """``SKILL.md`` — frontmatter advertisement plus the body."""
    frontmatter = "\n".join(
        [
            "---",
            f"name: {SKILL_NAME}",
            f"description: {DESCRIPTION}",
            f"version: {__version__}",
            "---",
        ]
    )
    return f"{frontmatter}\n\n{BODY}"


def default_dir(*, user: bool = False) -> Path:
    """Where the skill goes: this project's skills dir, or the user's."""
    base = Path.home() if user else Path.cwd()
    return base / ".claude" / "skills" / SKILL_NAME


def install(root: Path) -> Installed:
    """Write ``SKILL.md`` and the offline reference set into ``root``."""
    root = root.resolve()
    references = root / "references"
    references.mkdir(parents=True, exist_ok=True)

    written = [root / "SKILL.md"]
    (root / "SKILL.md").write_text(skill_markdown(), encoding="utf-8")

    # Progressive disclosure: SKILL.md is read when a task matches, and these
    # only when the agent needs the detail. Shipping them as files rather than
    # folding them into the body is what keeps the body cheap.
    for topic in docs.topics():
        path = references / f"{topic.name}.md"
        path.write_text(docs.render(topic.name), encoding="utf-8")
        written.append(path)

    return Installed(root=root, files=written)
