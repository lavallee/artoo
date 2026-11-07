"""Typed blocks inside Markdown content: the tier between prose and raw HTML.

Before blocks, an artifact either stayed in conservative Markdown or deleted
``[content]`` and owned every byte of ``site/`` as hand-written HTML. Most
pages need neither: they are prose with a handful of structured pieces — a
callout, a row of figures, a dense table bound to a data pack — and writing
those pieces as raw markup is where agents spend tokens and make the mistakes
the build later catches (an invented class, a stat with its label outside the
card, a table whose numbers were retyped from the data and drifted).

A block is a fenced directive::

    ::: callout warn #caveat title="Read this first"
    The 2024 file changed its denominator.
    :::

Each block is *declared* — name, attributes, body kind, example, renderer —
by the library whose vocabulary it emits, the same way ``Library.classes`` is.
That one declaration is the validator (an unknown attribute is a build error
naming the ones that exist), the renderer (output uses only classes the
library's stylesheet defines, which a test holds), and the docs (``artoo docs
blocks`` is generated from it). Errors carry ``file:line`` so the fix is one
edit, not a search.

Nesting uses colon count, as in Pandoc fenced divs: a block opened with
``::::`` closes only at ``::::``, so it can hold ordinary ``:::`` blocks.

``::: html`` is the declared escape hatch: its body is copied verbatim. It is
still subject to the invented-class check, static verification, the design
lint, and the browser checks, so ambition does not cost the safety net.
"""

from __future__ import annotations

import difflib
import html
import re
from collections.abc import Callable
from dataclasses import dataclass, field

OPEN = re.compile(r"^(:{3,})\s*([a-z][\w-]*)\s*(.*?)\s*$")
_TOKEN = re.compile(
    r"""\#(?P<id>[A-Za-z][\w-]*)"""
    r"""|(?P<key>[A-Za-z][\w-]*)=(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>\S+))"""
    r"""|"(?P<qword>[^"]*)"|(?P<word>\S+)"""
)
_FIRST_TAG = re.compile(r"^\s*<([a-zA-Z][\w-]*)")
# The first start tag, split before its closing ``>`` so attributes append
# after the ones the renderer wrote (class first reads better in the output).
_OPEN_TAG = re.compile(r"^(\s*<[a-zA-Z][\w-]*(?:\s[^<>]*?)?)(\s*/?>)")


@dataclass(frozen=True)
class Attr:
    name: str
    help: str
    required: bool = False
    choices: tuple[str, ...] = ()
    flag: bool = False  # a bare word sets it; it takes no value


@dataclass(frozen=True)
class Block:
    """One declared block. ``render`` receives a :class:`Call` and returns HTML."""

    name: str
    library: str
    summary: str
    render: Callable[[Call], str]
    attrs: tuple[Attr, ...] = ()
    body: str = "markdown"  # markdown | lines | raw | none
    # The attribute a single bare word fills, e.g. the callout variant.
    positional: str = ""
    example: str = ""
    styles: tuple[str, ...] = ()  # site-relative stylesheets the output needs
    scripts: tuple[str, ...] = ()  # site-relative scripts, loaded at the end of <body>

    def attr(self, name: str) -> Attr | None:
        return next((a for a in self.attrs if a.name == name), None)


@dataclass
class Context:
    """Per-render state: the registry, where diagnostics go, and what the page needs."""

    registry: dict[str, Block]
    source: str = "content.md"
    data_packs: list[dict] = field(default_factory=list)
    artifact_dir: object = None  # Path; untyped to keep this module import-light
    poster_exists: Callable[[str], bool] | None = None
    diagnostics: list[str] = field(default_factory=list)
    libraries: list[str] = field(default_factory=list)
    styles: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    counter: int = 0

    def error(self, line: int, message: str) -> None:
        self.diagnostics.append(f"{self.source}:{line}: {message}")

    def need(self, block: Block) -> None:
        if block.library and block.library not in self.libraries:
            self.libraries.append(block.library)
        for style in block.styles:
            if style not in self.styles:
                self.styles.append(style)
        for script in block.scripts:
            if script not in self.scripts:
                self.scripts.append(script)

    def need_script(self, script: str) -> None:
        if script not in self.scripts:
            self.scripts.append(script)

    def next_id(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}-{self.counter}"


@dataclass
class Call:
    """A block as written: its declaration, parsed attributes, body, and location."""

    block: Block
    attrs: dict[str, str]
    body: list[str]
    line: int  # 1-based line of the opening fence in the source file
    ctx: Context
    id: str = ""

    def get(self, name: str, default: str = "") -> str:
        return self.attrs.get(name, default)

    def flag(self, name: str) -> bool:
        return name in self.attrs

    def error(self, message: str, offset: int = 0) -> None:
        self.ctx.error(self.line + offset, f"`{self.block.name}` block: {message}")

    def markdown(self) -> str:
        """The body rendered as Markdown, with line numbers that still point at the file."""
        from .generators.notebook_report import markdown

        return markdown.to_html(
            "\n".join(self.body),
            poster_exists=self.ctx.poster_exists,
            blocks=self.ctx,
            line_offset=self.line,
        )

    def inline(self, text: str) -> str:
        from .generators.notebook_report import markdown

        return markdown.inline(text)

    def lines(self) -> list[tuple[int, str]]:
        """Non-blank body lines with their offset from the fence (1 = first body line)."""
        return [(n, raw.strip()) for n, raw in enumerate(self.body, 1) if raw.strip()]


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def parse_args(text: str) -> tuple[str, dict[str, str], list[str]]:
    """``#id``, ``key=value`` / ``key="quoted value"``, and bare words, in any order."""
    block_id, pairs, words = "", {}, []
    for match in _TOKEN.finditer(text):
        if match.group("id"):
            block_id = match.group("id")
        elif match.group("key"):
            value = match.group("dq")
            if value is None:
                value = match.group("sq")
            if value is None:
                value = match.group("bare") or ""
            pairs[match.group("key")] = value
        elif match.group("qword") is not None:
            words.append(match.group("qword"))
        else:
            words.append(match.group("word"))
    return block_id, pairs, words


def _suggest(name: str, known) -> str:
    match = difflib.get_close_matches(name, sorted(known), n=1, cutoff=0.6)
    return f' (did you mean "{match[0]}"?)' if match else ""


def _mark(fragment: str, call: Call) -> str:
    """Stamp the block's root element with its id and source coordinate.

    ``data-src`` is what lets a browser finding ("overflows at 390px") name the
    line in content.md that produced the element, instead of a selector the
    author never wrote.
    """
    extra = f' data-block="{call.block.name}" data-src="{esc(call.ctx.source)}:{call.line}"'
    if call.id:
        extra = f' id="{esc(call.id)}"' + extra
    return _OPEN_TAG.sub(lambda m: m.group(1) + extra + m.group(2), fragment, count=1)


def render(name: str, args: str, body: list[str], line: int, ctx: Context) -> str:
    """Validate one written block against its declaration, then render it."""
    block = ctx.registry.get(name)
    if block is None:
        ctx.error(
            line,
            f'unknown block "{name}"{_suggest(name, ctx.registry)} — '
            "`artoo docs blocks` lists the blocks this artifact can use",
        )
        return ""
    block_id, pairs, words = parse_args(args)
    attrs: dict[str, str] = {}
    ok = True
    for word in words:
        spec = block.attr(word)
        if spec is not None and spec.flag:
            attrs[word] = ""
        elif block.positional and block.positional not in attrs and block.positional not in pairs:
            attrs[block.positional] = word
        else:
            known = [a.name for a in block.attrs]
            ctx.error(
                line,
                f"`{name}` block: unexpected word {word!r}; "
                + (f"attributes are {', '.join(known)}" if known else "it takes no attributes"),
            )
            ok = False
    for key, value in pairs.items():
        spec = block.attr(key)
        if spec is None:
            known = [a.name for a in block.attrs]
            ctx.error(
                line,
                f"`{name}` block has no attribute {key!r}{_suggest(key, known)}; "
                + (f"it takes {', '.join(known)}" if known else "it takes none"),
            )
            ok = False
            continue
        if spec.flag:
            ctx.error(line, f"`{name}` block: {key} is a flag; write it bare, without =")
            ok = False
            continue
        attrs[key] = value
    for spec in block.attrs:
        value = attrs.get(spec.name)
        if spec.required and not value:
            ctx.error(line, f"`{name}` block needs {spec.name}= ({spec.help})")
            ok = False
        elif value is not None and spec.choices and value not in spec.choices:
            ctx.error(
                line,
                f"`{name}` block: {spec.name} {value!r} is not one of {', '.join(spec.choices)}",
            )
            ok = False
    if block.body == "none" and any(raw.strip() for raw in body):
        ctx.error(line, f"`{name}` block takes no body; move the text into an attribute")
        ok = False
    if not ok:
        return ""
    ctx.need(block)
    call = Call(block=block, attrs=attrs, body=body, line=line, ctx=ctx, id=block_id)
    fragment = block.render(call)
    return _mark(fragment, call) if fragment else ""


# -- the core escape hatch ---------------------------------------------------


def _html(call: Call) -> str:
    raw = "\n".join(call.body).strip("\n")
    if not raw.strip():
        call.error("is empty; put the markup between the fences or delete the block")
        return ""
    if not _FIRST_TAG.match(raw):
        # Text first would be wrapped by nothing; give the island a root so
        # data-src and an #id have somewhere to land.
        raw = f"<div>{raw}</div>"
    return raw


HTML = Block(
    name="html",
    library="",
    summary=(
        "raw HTML, copied verbatim — for the figure that carries the argument, or an "
        "interaction no block covers. "
        "Use kit classes and tokens (`var(--accent)`); the class check, verify, the design "
        "lint and the browser checks still apply"
    ),
    render=_html,
    body="raw",
    example=(
        '::: html #timeline\n<figure class="article-figure diagram">\n'
        '  <svg viewBox="0 0 320 40" role="img" aria-label="Spending rose each year">'
        '<rect class="timeline-bar" x="0" y="10" width="320" height="20"/></svg>\n'
        "</figure>\n:::"
    ),
)


def registry() -> dict[str, Block]:
    """Every block the installed libraries declare, plus the core ``html`` block."""
    from . import libraries

    found: dict[str, Block] = {}
    for lib in libraries.available().values():
        for block in lib.blocks:
            found.setdefault(block.name, block)
    found.setdefault(HTML.name, HTML)  # last: the escape hatch, not the first resort
    return found
