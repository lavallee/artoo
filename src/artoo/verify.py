"""Static and optional browser verification for a self-contained site."""

from __future__ import annotations

import html
import re
import tempfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import firewall, lint
from .manifest import Manifest

_REMOTE = re.compile(r"^(?:https?:)?//", re.I)
_CSS_REMOTE = re.compile(r"(?:@import\s+|url\(\s*['\"]?)(?:https?:)?//", re.I)
_CSS_URL = re.compile(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", re.I)
_CSS_IMPORT = re.compile(r"@import\s+['\"]([^'\"]+)['\"]", re.I)
_JS_REMOTE = re.compile(
    r"(?:(?:fetch|import)\s*\(\s*|(?:from|import)\s*)['\"](?:https?:)?//",
    re.I,
)


@dataclass
class VerificationResult:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    screenshots: list[Path] = field(default_factory=list)
    contact_sheet: Path | None = None
    pages: int = 0  # pages the browser opened
    skipped: str = ""  # why optional browser checks did not run

    @property
    def ok(self) -> bool:
        return not self.problems

    def merge(self, other: VerificationResult) -> VerificationResult:
        self.problems.extend(other.problems)
        self.warnings.extend(other.warnings)
        self.screenshots.extend(other.screenshots)
        self.contact_sheet = other.contact_sheet or self.contact_sheet
        self.pages = other.pages or self.pages
        self.skipped = other.skipped or self.skipped
        return self


@dataclass
class _Document:
    ids: set[str] = field(default_factory=set)
    refs: list[tuple[str, str, str]] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)
    missing_alt: int = 0
    empty_controls: int = 0
    tables: list[list[int]] = field(default_factory=list)
    table_headers: list[bool] = field(default_factory=list)
    diagrams: int = 0
    scripts: list[str] = field(default_factory=list)


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.doc = _Document()
        self._table: dict | None = None
        self._row_cells = 0
        self._button_depth = 0
        self._button_text = ""
        self._pre_depth = 0
        self._pre_counted = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            if element_id in self.doc.ids:
                self.doc.duplicate_ids.append(element_id)
            self.doc.ids.add(element_id)
        classes = set((values.get("class") or "").split())
        if tag == "pre":
            self._pre_depth += 1
            self._pre_counted = "mermaid" in classes
            self.doc.diagrams += self._pre_counted
        elif tag == "code" and self._pre_depth and "language-mermaid" in classes:
            self.doc.diagrams += not self._pre_counted
            self._pre_counted = True
        if tag == "script" and values.get("src"):
            self.doc.scripts.append(values["src"] or "")
        if tag == "img" and "alt" not in values:
            self.doc.missing_alt += 1
        if tag == "video" and not (values.get("aria-label") or values.get("title") or values.get("aria-labelledby")):
            self.doc.missing_alt += 1   # a video needs an accessible name, as an image needs alt
        if tag == "a" and values.get("href", "") in {"", "#"}:
            self.doc.empty_controls += 1
        if tag == "button":
            self._button_depth += 1
            self._button_text = values.get("aria-label", "") or values.get("title", "") or ""
        for attr in ("src", "href", "poster", "data", "action"):
            value = values.get(attr)
            if value:
                if tag == "link" and attr == "href":
                    rel = set((values.get("rel") or "").lower().split())
                    if not rel.intersection({"stylesheet", "icon", "preload", "modulepreload", "manifest"}):
                        continue
                self.doc.refs.append((tag, attr, value))
        for candidate in (values.get("srcset") or "").split(","):
            value = candidate.strip().split(" ", 1)[0]
            if value:
                self.doc.refs.append((tag, "srcset", value))
        if tag == "table":
            self._table = {"rows": [], "header": False}
        elif tag == "tr" and self._table is not None:
            self._row_cells = 0
        elif tag in {"td", "th"} and self._table is not None:
            self._row_cells += 1
            if tag == "th":
                self._table["header"] = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "pre" and self._pre_depth:
            self._pre_depth -= 1
        if tag == "tr" and self._table is not None and self._row_cells:
            self._table["rows"].append(self._row_cells)
        elif tag == "table" and self._table is not None:
            self.doc.tables.append(self._table["rows"])
            self.doc.table_headers.append(self._table["header"])
            self._table = None
        elif tag == "button" and self._button_depth:
            if not self._button_text.strip():
                self.doc.empty_controls += 1
            self._button_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._button_depth:
            self._button_text += data


def _rel(site: Path, path: Path) -> str:
    return str(path.relative_to(site))


def _target(site: Path, page: Path, url: str) -> tuple[Path | None, str]:
    parsed = urlsplit(url)
    if parsed.scheme or parsed.netloc:
        return None, parsed.fragment
    raw = unquote(parsed.path)
    if not raw:
        return page, parsed.fragment
    if raw.startswith("/"):
        return site / raw.lstrip("/"), parsed.fragment
    return page.parent / raw, parsed.fragment


def _diagram_problem(doc: _Document) -> str:
    """A Mermaid block with no renderer ships as a wall of source text."""
    if not doc.diagrams:
        return ""
    names = {urlsplit(src).path.rsplit("/", 1)[-1] for src in doc.scripts}
    if any("mermaid" in name for name in names):
        return ""  # mermaid.js (artoo-mermaid or a vendored copy) renders it
    missing = [name for name in ("pele.global.js", "diagrams.js") if name not in names]
    if not missing:
        return ""
    return (
        f"has {doc.diagrams} Mermaid block(s) but does not load "
        + " or ".join(f"lib/artoo-diagrams/{name}" for name in missing)
        + "; run `artoo lib add artoo-diagrams` and see `artoo docs artoo-diagrams`"
    )


def static(m: Manifest) -> VerificationResult:
    """Check files, links, anchors, IDs, offline resources, images, and tables."""
    result = VerificationResult()
    site = m.site_dir
    if not site.is_dir():
        result.problems.append(f"site root {site} does not exist; run `artoo build` after creating it")
        return result
    docs: dict[Path, _Document] = {}
    pages = [
        path
        for path in site.rglob("*.html")
        if firewall.is_publishable(path.relative_to(site))
    ]
    for page in sorted(pages):
        parser = _Parser()
        try:
            parser.feed(page.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            result.problems.append(f"could not read {_rel(site, page)}: {exc}")
            continue
        docs[page.resolve()] = parser.doc
        if _CSS_REMOTE.search(page.read_text(encoding="utf-8", errors="replace")):
            result.problems.append(
                f"{_rel(site, page)} loads a remote inline CSS resource; "
                "vendor it under site/lib/"
            )
        for duplicate in parser.doc.duplicate_ids:
            result.problems.append(f"{_rel(site, page)} repeats id={duplicate!r}; make every id unique")
        if parser.doc.missing_alt:
            result.warnings.append(
                f"{_rel(site, page)} has {parser.doc.missing_alt} image(s) without alt; "
                "use alt=\"\" for decorative images; name a video with aria-label"
            )
        if parser.doc.empty_controls:
            result.warnings.append(
                f"{_rel(site, page)} has {parser.doc.empty_controls} empty or nowhere-pointing control(s)"
            )
        problem = _diagram_problem(parser.doc)
        if problem:
            result.problems.append(f"{_rel(site, page)} {problem}")
        for index, rows in enumerate(parser.doc.tables):
            if not parser.doc.table_headers[index]:
                result.warnings.append(f"{_rel(site, page)} table {index + 1} has no <th> headings")
            widths = {width for width in rows if width}
            if len(widths) > 1:
                result.warnings.append(
                    f"{_rel(site, page)} table {index + 1} has uneven row widths {sorted(widths)}"
                )

    for page, doc in docs.items():
        for tag, attr, url in doc.refs:
            if url.startswith("javascript:"):
                result.problems.append(
                    f"{_rel(site, page)} uses a javascript: URL; bind behavior in a local script"
                )
                continue
            if url.startswith(("data:", "mailto:", "tel:")):
                continue
            runtime = attr in {"src", "srcset", "poster", "data", "action"} or tag == "link"
            if _REMOTE.match(url):
                if runtime:
                    result.problems.append(
                        f"{_rel(site, page)} loads {url} at runtime; vendor it under site/lib/"
                    )
                continue
            parsed = urlsplit(url)
            if parsed.scheme:
                continue
            if parsed.path.startswith("/"):
                result.problems.append(
                    f"{_rel(site, page)} uses root-relative {url}; use a relative URL so file:// works"
                )
            target, fragment = _target(site, page, url)
            if target is None:
                continue
            if target.is_dir():
                target = target / "index.html"
            target = target.resolve()
            try:
                target_rel = target.relative_to(site.resolve())
            except ValueError:
                result.problems.append(
                    f"{_rel(site, page)} references {url} outside build.site; "
                    "pack it into the publishable site"
                )
                continue
            if not firewall.is_publishable(target_rel):
                result.problems.append(
                    f"{_rel(site, page)} references firewall-withheld {url}; "
                    "move the asset into a publishable path"
                )
                continue
            if not target.is_file():
                result.problems.append(
                    f"{_rel(site, page)} references missing {url}; add the file or fix the {attr}"
                )
                continue
            if fragment and target.suffix.lower() in {".html", ".htm"}:
                target_doc = docs.get(target)
                if target_doc and fragment not in target_doc.ids:
                    result.problems.append(
                        f"{_rel(site, page)} links to missing anchor #{fragment} in {_rel(site, target)}"
                    )

    for path in sorted(site.rglob("*")):
        if not path.is_file() or not firewall.is_publishable(path.relative_to(site)):
            continue
        suffix = path.suffix.lower()
        if suffix == ".css":
            css = path.read_text(encoding="utf-8", errors="replace")
            css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
            if _CSS_REMOTE.search(css):
                result.problems.append(
                    f"{_rel(site, path)} loads a remote CSS resource; vendor it under site/lib/"
                )
            resources = set(_CSS_URL.findall(css)) | set(_CSS_IMPORT.findall(css))
            for url in sorted(resources):
                if url.startswith(("data:", "#")) or _REMOTE.match(url):
                    continue
                parsed = urlsplit(url)
                if parsed.scheme:
                    continue
                if parsed.path.startswith("/"):
                    result.problems.append(
                        f"{_rel(site, path)} uses root-relative CSS resource {url}; "
                        "use a relative URL so file:// works"
                    )
                target = (
                    site / parsed.path.lstrip("/")
                    if parsed.path.startswith("/")
                    else path.parent / unquote(parsed.path)
                ).resolve()
                try:
                    target_rel = target.relative_to(site.resolve())
                except ValueError:
                    result.problems.append(
                        f"{_rel(site, path)} references CSS resource {url} outside build.site"
                    )
                    continue
                if not firewall.is_publishable(target_rel):
                    result.problems.append(
                        f"{_rel(site, path)} references firewall-withheld CSS resource {url}"
                    )
                    continue
                if not target.is_file():
                    result.problems.append(
                        f"{_rel(site, path)} references missing CSS resource {url}"
                    )
        if suffix in {".js", ".mjs"} and _JS_REMOTE.search(
            path.read_text(encoding="utf-8", errors="replace")
        ):
            result.problems.append(
                f"{_rel(site, path)} fetches a remote runtime resource; pack it into the artifact"
            )
    # Design lint is taste written down as rules, so it warns and never fails;
    # only a typo in [verify] allow is a problem, because it silently allows nothing.
    result.problems.extend(lint.allow_problems(m))
    result.warnings.extend(finding.message() for finding in lint.check(m))
    return result


# ---- browser checks --------------------------------------------------------

VIEWPORTS = (("phone", 390, 844), ("desktop", 1440, 900))
# Messages per rule, page and viewport before the rest collapse into "and N more".
CAP = 3
INSTALL_HINT = (
    "`uv tool install artoo-artifacts --with-executables-from playwright`, "
    "then `playwright install chromium`"
)
# Long pages are screenshotted to this height: enough to judge the page, small
# enough that a forty-page collection does not write gigabytes.
SHOT_MAX_HEIGHT = 8000
SHEET_MAX_PAGES = 24

# rule -> (fails the build, what to do about it)
RULES: dict[str, tuple[bool, str]] = {
    "overflow": (True, "let it wrap, or put wide content in a scroll region (`article-table`)"),
    "image": (True, "the file is missing or is not an image; fix the src"),
    "diagram": (True, "check the Mermaid source and that lib/artoo-diagrams loads"),
    "clipped": (False, "give the box room or let the text wrap"),
    "small": (False, "set it to at least 12px"),
    "contrast": (False, "darken the text or lighten its background"),
    "overlap": (False, "move the positioned box or make room for it"),
}

_PROBE = Path(__file__).with_name("browser_probe.js").read_text(encoding="utf-8")


@dataclass
class Finding:
    """One browser finding, located as precisely as the page allows."""

    rule: str
    page: str
    viewports: list[str]
    what: str
    selector: str = ""
    heading: str = ""
    src: str = ""

    def where(self) -> str:
        parts = [f"`{self.selector}`"] if self.selector else []
        if self.heading:
            parts.append(f"§{self.heading}")
        if self.src:
            parts.append(self.src)
        return " ".join(parts)

    def message(self) -> str:
        where = self.where()
        return (
            f"{self.page} ({', '.join(self.viewports)}) {self.what}"
            + (f" at {where}" if where else "")
            + f"; {RULES[self.rule][1]}"
        )


def _quote(text: str) -> str:
    return f'"{text}"' if text else ""


def _describe(rule: str, item: dict) -> str:
    text = _quote(item.get("text", ""))
    if rule == "image":
        return f"broken image {item.get('detail', '')!r}"
    if rule == "diagram":
        return "Mermaid diagram did not render" + (f" ({text})" if text else "")
    if rule == "clipped":
        return f"text is clipped by its box: {text}"
    if rule == "small":
        return f"{item.get('size')}px text {text}"
    if rule == "contrast":
        return (
            f"contrast {item.get('ratio')}:1 is under {item.get('need'):g}:1 "
            f"({item.get('fg')} on {item.get('bg')}) for {text}"
        )
    if rule == "overlap":
        return (
            f"positioned text {text} sits over `{item.get('other', '')}` "
            f"{_quote(item.get('otherText', ''))}"
        ).rstrip()
    return rule


def _overflow_message(page: str, label: str, data: dict) -> str:
    named = []
    for item in data.get("offenders", []):
        where = Finding(
            "overflow", page, [label], "", item.get("sel", ""),
            item.get("heading", ""), item.get("src", ""),
        ).where()
        named.append(f"{where} reaches {item.get('right')}px")
    more = int(data.get("total", 0)) - len(named)
    detail = ""
    if named:
        detail = "; widest: " + ", ".join(named) + (f", and {more} more" if more > 0 else "")
    return (
        f"{page} overflows horizontally at {data.get('viewport')}px ({label}): the page is "
        f"{data.get('width')}px wide{detail}; {RULES['overflow'][1]}"
    )


def findings_from_probe(page: str, probes: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Turn per-viewport probe output into capped problem and warning messages.

    A finding that shows at both widths is one message naming both, so a
    contrast fault in a shared footer reads once per page, not twice.
    """
    problems: list[str] = []
    warnings: list[str] = []
    for label, data in probes.items():
        if data.get("overflow"):
            problems.append(_overflow_message(page, label, data["overflow"]))
    for rule in RULES:
        if rule == "overflow":
            continue
        merged: dict[tuple[str, str], Finding] = {}
        hidden: dict[str, int] = {}
        for label, data in probes.items():
            items = data.get(rule) or []
            # The probe returns a bounded sample; its count is the true total.
            hidden[label] = max(0, int((data.get("counts") or {}).get(rule, 0)) - len(items))
            for item in items:
                what = _describe(rule, item)
                key = (item.get("sel", ""), what)
                if key in merged:
                    if label not in merged[key].viewports:
                        merged[key].viewports.append(label)
                else:
                    merged[key] = Finding(
                        rule, page, [label], what, item.get("sel", ""),
                        item.get("heading", ""), item.get("src", ""),
                    )
        groups: dict[tuple[str, ...], list[Finding]] = {}
        for finding in merged.values():
            groups.setdefault(tuple(finding.viewports), []).append(finding)
        sink = problems if RULES[rule][0] else warnings
        for viewports, found in groups.items():
            sink.extend(finding.message() for finding in found[:CAP])
            more = len(found) - CAP
            if len(viewports) == 1:
                more += hidden.get(viewports[0], 0)
            if more > 0:
                sink.append(f"{page} ({', '.join(viewports)}) and {more} more {rule} finding(s)")
    return problems, warnings


def _console_line(message, site: Path) -> str:
    # The staged copy lives in a temp dir that is gone by the time anyone
    # reads this; name files as the site does.
    text = message.text.replace(site.resolve().as_uri() + "/", "")
    try:
        location = message.location or {}
    except Exception:  # noqa: BLE001 - a location is a nicety, never a reason to fail
        location = {}
    url = location.get("url") or ""
    if url.startswith("file://"):
        try:
            path = Path(unquote(urlsplit(url).path)).relative_to(site.resolve())
        except ValueError:
            return text
        line = location.get("lineNumber")
        text += f" (at {path}{':' + str(line + 1) if isinstance(line, int) else ''})"
    return text


def _shoot(page, dest: Path, width: int) -> None:
    height = page.evaluate(
        "Math.max(document.documentElement.scrollHeight, "
        "document.body ? document.body.scrollHeight : 0)"
    )
    if height and height > SHOT_MAX_HEIGHT:
        clip = {"x": 0, "y": 0, "width": width, "height": SHOT_MAX_HEIGHT}
        page.screenshot(path=str(dest), full_page=True, clip=clip)
    else:
        page.screenshot(path=str(dest), full_page=True)


def _sheet_html(shots: list[tuple[str, dict[str, Path]]], omitted: int) -> str:
    rows = []
    for page, images in shots:
        figures = []
        for label, width, _height in sorted(VIEWPORTS, key=lambda v: v[0] != "desktop"):
            image = images.get(label)
            if image:
                figures.append(
                    f'<figure class="{label}"><figcaption>{label} · {width}px</figcaption>'
                    f'<div class="crop"><img src="{image.resolve().as_uri()}" alt=""></div>'
                    "</figure>"
                )
        rows.append(
            f"<section><h2>{html.escape(page)}</h2><div class=pair>{''.join(figures)}</div>"
            "</section>"
        )
    if omitted:
        rows.append(
            f"<p class=more>and {omitted} more page(s); their screenshots sit beside this sheet</p>"
        )
    # Up to three pages a row keeps a large collection near a landscape page
    # instead of a strip too tall for anyone, or any model, to read at once.
    columns = 1 if len(shots) == 1 else 2 if len(shots) <= 4 else 3
    return (
        "<!doctype html><meta charset=utf-8><style>"
        "body{margin:0;padding:20px;background:#e9e7e2;color:#222;width:max-content;"
        "font:14px/1.3 system-ui,sans-serif;display:grid;gap:16px;"
        f"grid-template-columns:repeat({columns},max-content);align-items:start}}"
        "section{background:#fff;border:1px solid #ccc;padding:10px 14px 14px}"
        "h2{font:600 15px/1.2 ui-monospace,monospace;margin:0 0 8px}"
        ".pair{display:flex;gap:14px;align-items:flex-start}"
        "figure{margin:0}figcaption{font-size:12px;color:#555;margin:0 0 4px}"
        ".crop{overflow:hidden;max-height:600px;border:1px solid #bbb;background:#fff}"
        ".desktop .crop{width:480px}.phone .crop{width:200px}.crop img{display:block;width:100%}"
        ".more{font-style:italic;grid-column:1/-1}"
        "</style><body>" + "".join(rows)
    )


def _contact_sheet(instance, shots: list[tuple[str, dict[str, Path]]], dest: Path) -> None:
    """Compose one image of every page at both widths: the look-once review."""
    shown = shots[:SHEET_MAX_PAGES]
    with tempfile.TemporaryDirectory(prefix="artoo-sheet-") as temp:
        sheet = Path(temp) / "sheet.html"
        sheet.write_text(_sheet_html(shown, len(shots) - len(shown)), encoding="utf-8")
        context = instance.new_context(viewport={"width": 800, "height": 600})
        try:
            page = context.new_page()
            page.goto(sheet.as_uri(), wait_until="load")
            page.screenshot(path=str(dest), full_page=True)
        finally:
            context.close()


def _first_line(exc: Exception) -> str:
    text = str(exc).strip()
    return text.splitlines()[0] if text else type(exc).__name__


def browser(
    m: Manifest,
    *,
    screenshots: Path | None = None,
    optional: bool = False,
    fresh: bool = False,
) -> VerificationResult:
    """Open every publishable page in Chromium at phone and desktop widths.

    Playwright stays a soft dependency. When it is missing or Chromium will
    not launch, ``optional`` decides whether that is a problem (the caller
    asked for a browser) or only a note in ``result.skipped``. With
    ``screenshots``, each page is captured there and composed into one
    ``contact-sheet.png``; ``fresh`` first clears the PNGs a previous run left
    there, once Chromium has launched, so a skipped run keeps the last ones.
    """
    result = VerificationResult()

    def unavailable(reason: str, hint: str) -> VerificationResult:
        if optional:
            result.skipped = f"{reason} ({hint})"
        else:
            result.problems.append(
                f"browser verification needs Playwright and Chromium, but {reason}; {hint}"
            )
        return result

    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError:
        return unavailable("Playwright is not installed here", INSTALL_HINT)
    with tempfile.TemporaryDirectory(prefix="artoo-verify-") as temp:
        site = Path(temp) / "site"
        firewall.stage(m, site)
        pages = sorted(site.rglob("*.html"))
        probes: dict[str, dict[str, dict]] = {}
        shots: dict[str, dict[str, Path]] = {}
        with sync_playwright() as playwright:
            try:
                instance = playwright.chromium.launch()
            except Exception as exc:  # noqa: BLE001 - Playwright raises its own Error type
                return unavailable(
                    f"Chromium did not launch ({_first_line(exc)})",
                    "run `playwright install chromium`",
                )
            result.pages = len(pages)
            if screenshots:
                screenshots.mkdir(parents=True, exist_ok=True)
                if fresh:
                    # A screenshot of a page that no longer exists would sit
                    # beside the sheet looking current.
                    for old in screenshots.glob("*.png"):
                        old.unlink()
            try:
                for label, width, height in VIEWPORTS:
                    context = instance.new_context(viewport={"width": width, "height": height})
                    page = context.new_page()
                    errors: list[str] = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on(
                        "console",
                        lambda message: errors.append(_console_line(message, site))
                        if message.type == "error"
                        else None,
                    )
                    for path in pages:
                        rel = _rel(site, path)
                        try:
                            page.goto(path.resolve().as_uri(), wait_until="networkidle")
                        except Exception as exc:  # noqa: BLE001
                            result.problems.append(
                                f"browser could not open {rel} at {label}: {_first_line(exc)}"
                            )
                            errors.clear()
                            continue
                        try:
                            probes.setdefault(rel, {})[label] = page.evaluate(_PROBE)
                        except Exception as exc:  # noqa: BLE001 - a probe fault is ours
                            result.warnings.append(
                                f"browser checks could not inspect {rel} at {label}: "
                                f"{_first_line(exc)}"
                            )
                        for error in errors:
                            result.problems.append(f"{rel} browser error at {label}: {error}")
                        errors.clear()
                        if screenshots:
                            stem = "-".join(Path(rel).with_suffix("").parts)
                            dest = screenshots / f"{stem}-{label}.png"
                            _shoot(page, dest, width)
                            result.screenshots.append(dest)
                            shots.setdefault(rel, {})[label] = dest
                    context.close()
                if screenshots and shots:
                    result.contact_sheet = screenshots / "contact-sheet.png"
                    _contact_sheet(instance, list(shots.items()), result.contact_sheet)
            finally:
                instance.close()
    for rel, by_viewport in probes.items():
        problems, warnings = findings_from_probe(rel, by_viewport)
        result.problems.extend(problems)
        result.warnings.extend(warnings)
    return result


def run(
    m: Manifest,
    *,
    use_browser: bool = False,
    screenshots: Path | None = None,
) -> VerificationResult:
    result = static(m)
    if use_browser:
        result.merge(browser(m, screenshots=screenshots))
    return result


