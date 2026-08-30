"""Static and optional browser verification for a self-contained site."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import firewall
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

    @property
    def ok(self) -> bool:
        return not self.problems

    def merge(self, other: VerificationResult) -> VerificationResult:
        self.problems.extend(other.problems)
        self.warnings.extend(other.warnings)
        self.screenshots.extend(other.screenshots)
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


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.doc = _Document()
        self._table: dict | None = None
        self._row_cells = 0
        self._button_depth = 0
        self._button_text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            if element_id in self.doc.ids:
                self.doc.duplicate_ids.append(element_id)
            self.doc.ids.add(element_id)
        if tag == "img" and "alt" not in values:
            self.doc.missing_alt += 1
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
                "use alt=\"\" for decorative images"
            )
        if parser.doc.empty_controls:
            result.warnings.append(
                f"{_rel(site, page)} has {parser.doc.empty_controls} empty or nowhere-pointing control(s)"
            )
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
    return result


def browser(m: Manifest, *, screenshots: Path | None = None) -> VerificationResult:
    """Run Chromium checks when Playwright is installed; keep it an optional extra."""
    result = VerificationResult()
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError:
        result.problems.append(
            "browser verification needs Playwright; install `playwright` and run "
            "`playwright install chromium`, or omit --browser"
        )
        return result
    if screenshots:
        screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="artoo-verify-") as temp:
        site = Path(temp) / "site"
        firewall.stage(m, site)
        pages = sorted(site.rglob("*.html"))
        with sync_playwright() as playwright:
            instance = playwright.chromium.launch()
            try:
                for width, height, label in ((390, 844, "phone"), (1440, 900, "desktop")):
                    context = instance.new_context(viewport={"width": width, "height": height})
                    page = context.new_page()
                    errors: list[str] = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on(
                        "console",
                        lambda message: errors.append(message.text)
                        if message.type == "error"
                        else None,
                    )
                    for path in pages:
                        rel = _rel(site, path)
                        try:
                            page.goto(path.resolve().as_uri(), wait_until="networkidle")
                        except Exception as exc:
                            result.problems.append(
                                f"browser could not open {rel} at {label}: {exc}"
                            )
                            continue
                        overflow = page.evaluate(
                            "document.documentElement.scrollWidth > "
                            "document.documentElement.clientWidth + 1"
                        )
                        if overflow:
                            result.problems.append(
                                f"{rel} overflows horizontally at {width}px ({label})"
                            )
                        for error in errors:
                            result.problems.append(f"{rel} browser error at {label}: {error}")
                        errors.clear()
                        if screenshots:
                            stem = "-".join(Path(rel).with_suffix("").parts)
                            dest = screenshots / f"{stem}-{label}.png"
                            page.screenshot(path=str(dest), full_page=True)
                            result.screenshots.append(dest)
                    context.close()
            finally:
                instance.close()
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
