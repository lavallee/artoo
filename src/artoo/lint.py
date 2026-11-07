"""Design lint: named, deterministic checks for the habits that make a page look generated.

The invented-class check (``markup.py``) catches markup the stylesheet cannot
render. This catches markup it renders all too well: gradient headline text,
frosted-glass panels, emoji bullets, "01 /" eyebrows, colours and fonts typed
in by hand instead of taken from the kit's tokens, stock model copy. None of it
breaks a page, so none of it fails a build — every finding is a warning. The
point is that the rules are written down once, here, with the fix beside each,
instead of living in a prompt as advice an author may or may not have read.

Rules are deliberately narrow. A check that fires on legitimate work gets
ignored on the day it is right, so each one was calibrated against the real
artifacts on disk and trimmed until what it reports is almost always the thing
it names. An artifact that breaks a rule on purpose says so in
``[verify] allow``, which keeps the exception visible in the manifest.

Vendored libraries (``site/lib/``) are never linted: their CSS is where the
tokens are defined, so raw values there are the point.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from . import firewall
from .manifest import Manifest


@dataclass(frozen=True)
class Rule:
    id: str
    summary: str
    fix: str


RULES: dict[str, Rule] = {
    rule.id: rule
    for rule in (
        Rule(
            "raw-color",
            "a hex, rgb(), or hsl() colour typed into page CSS or a style= attribute",
            "use a kit token — var(--text), var(--muted), var(--accent), var(--surface), "
            "var(--border), var(--chart-1)…var(--chart-8) — or define your own once as a "
            "custom property (--brand: #…) and use var(--brand)",
        ),
        Rule(
            "foreign-font",
            "a font-family that names a web font, or sets a family without a kit font token",
            "use var(--font-prose), var(--font-ui), var(--font-display), or "
            "var(--font-numeric); the kit stacks are offline system fonts",
        ),
        Rule(
            "gradient-text",
            "text painted with a gradient via background-clip: text",
            "give the text a solid colour such as var(--text) or var(--accent); "
            "let size and weight carry the emphasis",
        ),
        Rule(
            "glass",
            "a frosted-glass panel: backdrop-filter with blur()",
            "use an opaque surface: background: var(--surface); border: 1px solid "
            "var(--border)",
        ),
        Rule(
            "emoji-icon",
            "a heading, list item, button, or nav link whose text starts with an emoji",
            "drop the emoji and let the words lead; if an icon earns its place, use an "
            "inline SVG with aria-hidden=\"true\"",
        ),
        Rule(
            "numbered-eyebrow",
            "a counter used as decoration: an element that is only \"01\" / \"02 —\", "
            "or a heading that starts \"01.\"",
            "drop the counter and name the section; if order matters, use an <ol> "
            "(or class=\"toc\" for contents)",
        ),
        Rule(
            "card-as-container",
            "a nav-card (or card) that is not a link and holds no link",
            "nav-card is for links to destinations: make it <a class=\"nav-card\" "
            "href=…>, or use a plain <section> or class=\"callout\" for content",
        ),
        Rule(
            "stock-copy",
            "a stock phrase of generated prose (\"delve\", \"seamless integration\", "
            "\"unlock the power\", \"it's not just X, it's Y\" …)",
            "say the specific thing in plain words: what it does, for whom, by how much",
        ),
    )
}


@dataclass
class Finding:
    path: str  # artifact-relative, e.g. site/index.html
    line: int
    rule: str
    detail: str
    more: int = 0  # further hits of this rule in this file, past the cap

    def message(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        tail = f" (and {self.more} more in this file)" if self.more else ""
        return f"{where} [{self.rule}] {self.detail}{tail} — {RULES[self.rule].fix}"


# Past three hits a rule has made its point about a file, and past five files
# about the artifact; the rest is noise that buries every other warning. A
# generated site of 300 pages sharing one inline <style> says it once.
CAP = 3
FILE_CAP = 5

# -- CSS ---------------------------------------------------------------------

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_BODY = re.compile(r"\{([^{}]*)\}")
_HEX = re.compile(r"(?<![\w&-])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")
_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")  # content: "#1" is text, not a colour
_FUNC = re.compile(r"\b(?:rgba?|hsla?)\(", re.I)
_KEYWORDS = {"inherit", "initial", "unset", "revert", "revert-layer"}
# Families an author reaches for from Google Fonts or a framework default. The
# kit's own stacks name system fonts (Roboto appears in --font-ui as a system
# fallback), so a family is only "foreign" when the declaration is not a token.
_WEB_FONTS = re.compile(
    r"\b(?:inter|roboto|poppins|montserrat|open sans|lato|space grotesk|ibm plex \w+|"
    r"dm sans|dm serif \w+|nunito|raleway|work sans|manrope|outfit|plus jakarta sans|"
    r"source sans pro|source serif pro|playfair display|fraunces|geist|jetbrains mono|"
    r"fira code|fira sans|merriweather|lora|instrument serif|syne|sora)\b",
    re.I,
)


def _strip_calls(value: str, name: str) -> str:
    """Remove every ``name(...)`` call, balancing parens.

    A ``var(--x, #fff)`` fallback is the token pattern working as intended, and
    ``url(#gradient)`` is a reference, not a colour; neither should read as a
    raw literal.
    """
    out = []
    i = 0
    lowered = value.lower()
    needle = name + "("
    while i < len(value):
        boundary = i == 0 or not (value[i - 1].isalnum() or value[i - 1] in "-_")
        if boundary and lowered.startswith(needle, i):
            depth = 0
            j = i + len(name)
            while j < len(value):
                if value[j] == "(":
                    depth += 1
                elif value[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            i = j + 1
            out.append(" ")
            continue
        out.append(value[i])
        i += 1
    return "".join(out)


def _declarations(css: str, line: int = 1):
    """Yield ``(block, prelude, property, value, line)`` for each declaration in ``css``.

    Comments are blanked rather than removed so offsets — and therefore line
    numbers — survive. Innermost brace bodies are the declaration blocks; the
    text before each is its selector or at-rule.
    """
    css = _COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), css)
    for block, match in enumerate(_BODY.finditer(css)):
        start = match.start()
        prelude = re.split(r"[{};]", css[:start])[-1].strip().lower()
        body = match.group(1)
        offset = match.start(1)
        for part in re.finditer(r"[^;]+", body):
            decl = part.group(0)
            if ":" not in decl:
                continue
            prop, value = decl.split(":", 1)
            prop = prop.strip().lower()
            if not re.fullmatch(r"-?-?[\w-]+", prop):
                continue
            at = offset + part.start() + (len(decl) - len(decl.lstrip()))
            yield block, prelude, prop, value.strip(), line + css.count("\n", 0, at)


def _inline_declarations(style: str, line: int):
    for part in style.split(";"):
        if ":" in part:
            prop, value = part.split(":", 1)
            yield 0, "", prop.strip().lower(), value.strip(), line


def _css_findings(decls) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    decls = list(decls)
    # A translucent sticky bar that blurs what scrolls beneath it is a
    # legibility device, and it is nearly every backdrop-filter in practice.
    # Glassmorphism is the frosted panel sitting in the flow.
    # A scrim behind a modal (::backdrop) and a near-opaque surface blur for
    # the same reason; neither reads as glass.
    plain_blocks = {
        block
        for block, prelude, prop, value, _ in decls
        if (prop == "position" and value.split()[:1] in (["sticky"], ["fixed"]))
        or (prop in {"background", "background-color"} and _opacity(value) >= 0.85)
        or "::backdrop" in prelude
    }
    for block, prelude, prop, value, line in decls:
        if prelude.startswith(("@font-face", "@property")):
            continue  # declaring a family or a typed token is not using it
        bare = value.replace("!important", "").strip()
        if prop.startswith("--"):
            # Defining a token once is the right pattern; only a web font
            # smuggled in as a token is worth naming.
            if "font" in prop and _web_font(bare, False) and "var(" not in bare:
                found.append((line, "foreign-font", f"{prop}: {_short(bare)}"))
            continue
        if prop.lstrip("-").startswith(("webkit-mask", "mask")):
            plain = ""  # a mask reads only alpha; #000 there is not a colour choice
        else:
            plain = _QUOTED.sub(" ", _strip_calls(_strip_calls(bare, "var"), "url"))
        if _HEX.search(plain) or _FUNC.search(plain):
            found.append((line, "raw-color", f"{prop}: {_short(bare)}"))
        if prop == "font-family" or (prop == "font" and "," in bare):
            # Any token passes: the artifact's own --serif is the define-once
            # pattern, and a web font inside it is caught at its definition.
            web = _web_font(_strip_calls(bare, "var"), prop == "font")
            if web or ("var(" not in bare and bare.lower() not in _KEYWORDS):
                found.append((line, "foreign-font", f"{prop}: {_short(bare)}"))
        if prop in {"background-clip", "-webkit-background-clip"} and "text" in bare.lower():
            found.append((line, "gradient-text", f"{prop}: {bare}"))
        if prop in {"backdrop-filter", "-webkit-backdrop-filter"} and block not in plain_blocks:
            if re.search(r"blur\(\s*(?!0(?:px)?\s*\))", bare):
                found.append((line, "glass", f"{prop}: {bare}"))
    return found


def _opacity(value: str) -> float:
    """Best-effort alpha of a background value; 1.0 when it names no translucency."""
    value = _strip_calls(value.lower(), "var")
    mix = re.search(r"color-mix\([^)]*?(\d+(?:\.\d+)?)%[^)]*transparent", value)
    if mix:
        return float(mix.group(1)) / 100
    alpha = re.search(r"(?:rgba|hsla)\([^)]*,\s*([\d.]+)(%?)\s*\)|/\s*([\d.]+)(%?)\s*\)", value)
    if alpha:
        number, percent = (alpha.group(1), alpha.group(2)) if alpha.group(1) else alpha.group(3, 4)
        return float(number) / (100 if percent else 1)
    hex8 = re.search(r"#[0-9a-f]{6}([0-9a-f]{2})\b", value)
    if hex8:
        return int(hex8.group(1), 16) / 255
    return 0.0 if "transparent" in value else 1.0


def _web_font(value: str, shorthand: bool) -> bool:
    """Does the stack *lead* with a web font?

    Only the first family is the one chosen; Roboto or Helvetica further down
    is a system fallback (the kit's own --font-ui lists Roboto for Android).
    """
    if shorthand:
        match = re.search(r"\d[\w.%]*(?:\s*/\s*[\w.%]+)?\s+(.+)$", value)
        value = match.group(1) if match else value
    first = value.split(",")[0].strip().strip("'\"")
    return bool(_WEB_FONTS.fullmatch(first))


def _short(value: str, limit: int = 60) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


# -- HTML --------------------------------------------------------------------

# Emoji by Unicode block, plus the BMP characters whose default presentation
# is emoji. Arrows, check marks (✓ ✔), stars, and box symbols are ordinary
# typography and stay out unless written with the emoji selector U+FE0F.
_EMOJI_PLANE = (0x1F000, 0x1FAFF)
_EMOJI_BMP = set(
    "⌚⌛⏩⏪⏫⏬⏰⏳☔☕♈♉♊♋♌♍♎♏♐♑♒♓♿⚓⚡⚪⚫⚽⚾⛄⛅⛎⛔⛪⛲⛳⛵⛺⛽✅✊✋✨❌❎❓❔❕❗➕➖➗➰➿⬛⬜⭐⭕"
)
_SYMBOL_RANGES = ((0x2300, 0x23FF), (0x2600, 0x27BF), (0x2B00, 0x2BFF))


def _emoji_at_start(text: str) -> str:
    text = text.lstrip()
    if not text:
        return ""
    ch = text[0]
    code = ord(ch)
    if _EMOJI_PLANE[0] <= code <= _EMOJI_PLANE[1] or ch in _EMOJI_BMP:
        return ch
    if len(text) > 1 and text[1] == "️":
        if any(lo <= code <= hi for lo, hi in _SYMBOL_RANGES):
            return ch
    return ""


_EYEBROW = re.compile(r"[/#№]?\s*0[1-9]\s*[.·:—–\-/|)]?")
_HEADING_COUNTER = re.compile(r"0[1-9](?:\s*[.·:—–\-/|)]\s*|\s+)\S")
_EYEBROW_TAGS = {"span", "div", "p", "small", "strong", "b", "em", "i", "mark", "header"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_ICON_TAGS = _HEADINGS | {"li", "button"}
_SKIP_TEXT = {"script", "style", "pre", "code", "kbd", "samp", "textarea", "template", "svg"}
_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
    "track", "wbr",
}
_AUTOCLOSE = {"p", "li", "dt", "dd", "option", "tr", "td", "th"}

_APOS = "['’]"
_STOCK = [
    (re.compile(r"\bdelv(?:e|es|ed|ing)\b", re.I), "delve"),
    (re.compile(rf"\bin today{_APOS}s (?:fast-paced|rapidly|ever-changing|digital)", re.I),
     "in today's fast-paced …"),
    (re.compile(r"\bunlock(?:s|ing)? the (?:full )?(?:power|potential)\b", re.I),
     "unlock the power"),
    (re.compile(r"\bharness(?:es|ing)? the (?:full )?power\b", re.I), "harness the power"),
    # Bare "seamless" is ordinary technical English ("less seamless resume");
    # the stock phrase is the marketing pairing.
    (re.compile(r"\bseamless(?:ly)? (?:integrat\w*|experience|workflow|transition)", re.I),
     "seamless …"),
    (re.compile(r"\bgame[- ]chang(?:er|ing)\b", re.I), "game-changer"),
    (re.compile(rf"\blet{_APOS}s dive (?:in|into|deeper)\b", re.I), "let's dive in"),
    (re.compile(r"\belevate your\b", re.I), "elevate your"),
    (re.compile(r"\ba testament to\b", re.I), "a testament to"),
    (re.compile(r"\bnavigat(?:e|ing) the complexities\b", re.I), "navigate the complexities"),
    (re.compile(r"\bever-evolving landscape\b", re.I), "ever-evolving landscape"),
    (re.compile(
        rf"\b(?:it{_APOS}s|it is|this is|this isn{_APOS}t)\s+not\s+just\b[^.!?]{{1,80}}?"
        rf"[,;—–]\s*(?:it{_APOS}s|it is)\b",
        re.I,
    ), "it's not just … it's …"),
]


class _Element:
    __slots__ = ("tag", "line", "classes", "text", "has_link", "icon_pending", "nav", "reported")

    def __init__(self, tag: str, line: int, classes: set[str], nav: bool) -> None:
        self.tag = tag
        self.line = line
        self.classes = classes
        self.text: list[str] = []
        self.has_link = tag == "a"
        self.icon_pending = False
        self.nav = nav
        self.reported = ""


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[int, str, str]] = []
        self.stack: list[_Element] = []
        self._style: list[str] | None = None
        self._style_line = 0
        self._skip = 0
        self._kit = False
        self._cards: list[tuple[int, str, str]] = []

    # The stack is a forgiving approximation of the DOM: unclosed <p>/<li>
    # close when a sibling opens, and a stray end tag closes up to its match.
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line = self.getpos()[0]
        values = {k: v or "" for k, v in attrs}
        style = values.get("style")
        if style:
            raw = self.get_starttag_text() or ""
            at = line + raw[: max(raw.lower().find("style"), 0)].count("\n")
            self.found.extend(_css_findings(_inline_declarations(style, at)))
        if tag == "style":
            self._style = []
            self._style_line = line
            return
        if tag == "link" and "artoo-kit/" in values.get("href", ""):
            self._kit = True
        if tag in _VOID:
            if tag in {"img", "input"}:
                self._settle_icon()
            return
        if tag in _AUTOCLOSE and self.stack and self.stack[-1].tag == tag:
            self._close(self.stack.pop())
        nav = tag == "nav" or (bool(self.stack) and self.stack[-1].nav)
        element = _Element(tag, line, set(values.get("class", "").split()), nav)
        if tag in _SKIP_TEXT:
            self._skip += 1
        if tag == "a":
            for open_el in self.stack:
                open_el.has_link = True
        if tag in _ICON_TAGS or (tag == "a" and nav):
            element.icon_pending = True
        elif tag in {"svg", "img"}:
            self._settle_icon()  # a real icon first means the text is not the icon
        self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID and tag != "style" and self.stack and self.stack[-1].tag == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "style" and self._style is not None:
            css = "".join(self._style)
            self.found.extend(_css_findings(_declarations(css, self._style_line)))
            self._style = None
            return
        if not any(el.tag == tag for el in self.stack):
            return
        while self.stack:
            element = self.stack.pop()
            self._close(element)
            if element.tag == tag:
                break

    def _close(self, element: _Element) -> None:
        if element.tag in _SKIP_TEXT:
            self._skip -= 1
        text = " ".join("".join(element.text).split())
        parent = self.stack[-1] if self.stack else None
        if parent is not None:
            parent.text.append("".join(element.text))
        if element.reported and element.reported == text:
            if parent is not None:
                parent.reported = text
        elif element.tag in _EYEBROW_TAGS | _HEADINGS and text and _EYEBROW.fullmatch(text):
            self.found.append((element.line, "numbered-eyebrow", f"<{element.tag}> {text!r}"))
            if parent is not None:
                parent.reported = text
        # "03 · Copywriting" as an h1, or as the title of a link to
        # assessments/03.html, is a numbered document's name — an identifier,
        # not decoration. Calibration found those were most heading hits.
        elif (
            element.tag in _HEADINGS - {"h1"}
            and not element.reported
            and not element.has_link
            and not any(el.tag == "a" for el in self.stack)
            and _HEADING_COUNTER.match(text)
        ):
            self.found.append(
                (element.line, "numbered-eyebrow", f"<{element.tag}> {_short(text, 40)!r}")
            )
        if (
            element.classes & {"nav-card", "card"}
            and element.tag != "a"
            and not element.has_link
        ):
            cls = "nav-card" if "nav-card" in element.classes else "card"
            self._cards.append(
                (element.line, "card-as-container", f"<{element.tag} class=\"{cls}\"> with no link")
            )

    def _settle_icon(self) -> None:
        for element in self.stack:
            element.icon_pending = False

    def handle_data(self, data: str) -> None:
        if self._style is not None:
            self._style.append(data)
            return
        if not self.stack:
            return
        self.stack[-1].text.append(data)
        if self._skip or not data.strip():
            return
        line = self.getpos()[0]
        pending = [el for el in self.stack if el.icon_pending]
        if pending:
            emoji = _emoji_at_start(data)
            if emoji:
                el = pending[-1]
                label = "<a> in <nav>" if el.tag == "a" else f"<{el.tag}>"
                self.found.append((line, "emoji-icon", f"{label} starts with {emoji}"))
            self._settle_icon()
        for pattern, name in _STOCK:
            for match in pattern.finditer(data):
                at = line + data.count("\n", 0, match.start())
                self.found.append((at, "stock-copy", f"{name!r} in {_short(match.group(0), 50)!r}"))

    def close(self) -> None:
        super().close()
        while self.stack:
            self._close(self.stack.pop())
        # A page's own .card is its business unless artoo-kit is loaded, where
        # .card is the deprecated alias of nav-card and styles as a link.
        self.found.extend(c for c in self._cards if self._kit or "nav-card" in c[2])


# -- running it ----------------------------------------------------------------


def allow_problems(m: Manifest) -> list[str]:
    """Unknown ids in ``[verify] allow`` — a typo there silently allows nothing."""
    known = ", ".join(RULES)
    return [
        f"verify.allow names unknown lint rule {rule!r}; known rules: {known}"
        for rule in m.verify_allow
        if isinstance(rule, str) and rule not in RULES
    ]


def _own_files(site: Path):
    """Publishable HTML and CSS the artifact wrote itself — never site/lib/."""
    for path in sorted(site.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".html", ".htm", ".css"}:
            continue
        rel = path.relative_to(site)
        if rel.parts[0] == "lib" or not firewall.is_publishable(rel):
            continue
        yield path, rel


def lint_html(text: str) -> list[tuple[int, str, str]]:
    page = _Page()
    page.feed(text)
    page.close()
    return page.found


def lint_css(text: str) -> list[tuple[int, str, str]]:
    return _css_findings(_declarations(text))


def check(m: Manifest) -> list[Finding]:
    """Design-lint findings across the artifact's own pages and stylesheets.

    Unknown ids in ``[verify] allow`` are reported by :func:`allow_problems`;
    known ones are skipped here.
    """
    site = m.site_dir
    if not site.is_dir():
        return []
    allowed = set(m.verify_allow)
    by_rule: dict[str, list[list[Finding]]] = {}
    for path, rel in _own_files(site):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue  # verify.static reports unreadable pages
        hits = lint_css(text) if path.suffix.lower() == ".css" else lint_html(text)
        shown = str(Path(m.site) / rel)
        per_rule: dict[str, list[Finding]] = {}
        for line, rule, detail in sorted(hits):
            if rule not in allowed:
                per_rule.setdefault(rule, []).append(Finding(shown, line, rule, detail))
        for rule, found in per_rule.items():
            by_rule.setdefault(rule, []).append(found)

    findings: list[Finding] = []
    for rule in RULES:
        files = by_rule.get(rule, [])
        for found in files[:FILE_CAP]:
            kept = found[:CAP]
            kept[-1].more = len(found) - len(kept)
            findings.extend(kept)
        rest = files[FILE_CAP:]
        if rest:
            count = sum(len(found) for found in rest)
            plural = "s" if len(rest) > 1 else ""
            findings.append(
                Finding(f"{m.site}/", 0, rule, f"{count} more in {len(rest)} other file{plural}")
            )
    return findings
