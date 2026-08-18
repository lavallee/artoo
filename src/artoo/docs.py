"""``artoo docs``: the contract, on demand.

The reference material for authoring an artifact used to live in three places
an author working in *another* repo could not reach — module docstrings, the
library READMEs inside the installed wheel, and DESIGN.md in the artoo repo.
The predictable result was reverse-engineering: read four stylesheets, or copy
a previous artifact and hope its layout was right.

So the contract ships with the tool and answers to one command. Authored
guides live under ``reference/``; each site library contributes a topic of its
own, assembled from its prose contract plus a class table generated from
``Library.classes``. The generated half is why this can be trusted — a test
holds that table against the stylesheets, so the docs cannot describe a class
the CSS no longer defines.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import libraries as libraries_mod

REFERENCE_DIR = Path(__file__).parent / "reference"

# Ordered: reading them top to bottom is a coherent introduction.
AUTHORED = {
    "quickstart": "Install, the golden path, and the authoring rules that matter.",
    "manifest": "Every artifact.toml key, and what the validator enforces.",
    "firewall": "What publishes, what is withheld, and why it is structural.",
    "provenance": "Attaching a flip notebook, the projection, and the roundtrip verbs.",
    "generators": "Plugin generators, worker tiers, and the two built in.",
}


@dataclass(frozen=True)
class Topic:
    name: str
    summary: str
    is_library: bool = False


def topics() -> list[Topic]:
    """Every readable topic: the authored guides, then one per site library."""
    found = [
        Topic(name, summary)
        for name, summary in AUTHORED.items()
        if (REFERENCE_DIR / f"{name}.md").is_file()
    ]
    for name, lib in sorted(libraries_mod.available().items()):
        found.append(Topic(name, lib.summary or f"The {name} site library.", is_library=True))
    return found


def class_table(lib: libraries_mod.Library) -> str:
    """The library's public vocabulary as a markdown table."""
    if not lib.classes:
        return ""
    rows = "\n".join(f"| `{cls}` | {role} |" for cls, role in lib.classes.items())
    table = f"| class | role |\n|---|---|\n{rows}"
    if not lib.namespaces:
        return table
    owned = ", ".join(f"`{namespace}`" for namespace in lib.namespaces)
    return (
        f"{table}\n\n"
        f"{lib.name} owns {owned}. A class starting with one of those that the "
        f"vendored stylesheet does not define is a guess, and `artoo build` "
        f"reports it with the nearest real class. Your own classes belong "
        f"outside those prefixes."
    )


def _strip_title(text: str) -> str:
    """Drop a leading H1 so the composed page has exactly one."""
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines)


def render(name: str) -> str:
    """The full text of one topic."""
    path = REFERENCE_DIR / f"{name}.md"
    if name in AUTHORED and path.is_file():
        return path.read_text(encoding="utf-8").rstrip() + "\n"

    try:
        lib = libraries_mod.get(name)
    except KeyError:
        known = ", ".join(topic.name for topic in topics())
        raise KeyError(f"no docs topic named {name!r} (topics: {known})") from None

    parts = [f"# {lib.name} {lib.version}"]
    if lib.summary:
        parts.append(lib.summary)
    if lib.reference and lib.reference.is_file():
        parts.append(_strip_title(lib.reference.read_text(encoding="utf-8")).rstrip())
    table = class_table(lib)
    if table:
        parts.append(f"## Class vocabulary\n\n{table}")
    return "\n\n".join(part for part in parts if part).rstrip() + "\n"


def index() -> str:
    """The topic list, as markdown."""
    found = topics()
    width = max(len(topic.name) for topic in found)
    guides = [t for t in found if not t.is_library]
    libs = [t for t in found if t.is_library]
    lines = ["# artoo docs", "", "Read a topic with `artoo docs <topic>`.", "", "## Guides", ""]
    lines += [f"  {t.name.ljust(width)}  {t.summary}" for t in guides]
    lines += ["", "## Site libraries", ""]
    lines += [f"  {t.name.ljust(width)}  {t.summary}" for t in libs]
    lines += [
        "",
        "Library topics list every class the library defines, with its role, so",
        "markup does not have to be guessed from the stylesheets.",
        "",
    ]
    return "\n".join(lines)


def _with_anchor(name: str, text: str) -> str:
    """Name the topic under its own heading.

    Concatenated, the topics lose the one thing the index gave them: a handle.
    A reader (or a model) that wants to re-read just one section, or cite where
    a rule came from, needs the topic name present in the text — the prose
    heading alone does not carry it.
    """
    lines = text.rstrip().splitlines()
    if lines and lines[0].startswith("# "):
        return "\n".join([lines[0], "", f"*On its own: `artoo docs {name}`*", *lines[1:]])
    return text.rstrip()


def render_all() -> str:
    """Every topic concatenated — the whole contract in one read."""
    chunks = [
        "# artoo — the complete reference",
        "",
        "Generated by `artoo docs --all`. Each section is also readable on its",
        "own with `artoo docs <topic>`.",
    ]
    for topic in topics():
        chunks.append("\n---\n")
        chunks.append(_with_anchor(topic.name, render(topic.name)))
    return "\n".join(chunks).rstrip() + "\n"


# -- the published reference ------------------------------------------------

SITE_URL = "https://lavallee.github.io/artoo"


def llms_txt(base_url: str = SITE_URL) -> str:
    """An ``llms.txt`` index of the published reference.

    The convention (llmstxt.org) is a markdown index at a well-known path: a
    model or crawler that lands on the project can find the reference without
    scraping a rendered page for it. Cheap to publish, and it makes the same
    contract reachable from outside a shell — the case ``artoo docs`` cannot
    serve, because it needs artoo installed.
    """
    lines = [
        "# artoo",
        "",
        "> Generate and manage artifacts: self-contained HTML mini-sites that pair "
        "presentation with the research backing it. An artifact is a directory with "
        "an artifact.toml, renders from a file:// URL, and keeps its research beside "
        "the presentation behind a deny-by-default deploy firewall.",
        "",
        "With artoo installed, the same reference is available offline as "
        "`artoo docs <topic>`, and `artoo init` writes the layout contract into "
        "each artifact it creates as AGENTS.md.",
        "",
        "## Guides",
        "",
    ]
    guides = [t for t in topics() if not t.is_library]
    libs = [t for t in topics() if t.is_library]
    lines += [f"- [{t.name}]({base_url}/reference/{t.name}.md): {t.summary}" for t in guides]
    lines += ["", "## Site libraries", ""]
    lines += [f"- [{t.name}]({base_url}/reference/{t.name}.md): {t.summary}" for t in libs]
    lines += [
        "",
        "## Optional",
        "",
        f"- [Complete reference]({base_url}/llms-full.txt): every topic in one file.",
        "",
    ]
    return "\n".join(lines)


def write_site(docs_dir: Path, base_url: str = SITE_URL) -> list[Path]:
    """Render the reference into a docs site: llms.txt, llms-full.txt, reference/."""
    reference = docs_dir / "reference"
    reference.mkdir(parents=True, exist_ok=True)
    written = []
    for topic in topics():
        path = reference / f"{topic.name}.md"
        path.write_text(render(topic.name), encoding="utf-8")
        written.append(path)
    for name, text in (("llms.txt", llms_txt(base_url)), ("llms-full.txt", render_all())):
        path = docs_dir / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return sorted(written)
