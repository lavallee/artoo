"""A local server for artifacts that have to remember something.

Most artifacts are finished the moment they render, and `file://` is the right
way to read them. Explorers are the exception: a page whose value is the
configuration a reader arrived at — a set of weights, a chosen comparison, a
saved view — is only useful the second time if that configuration survives.

Browser storage is the cheap answer and the wrong one. It is per-browser,
invisible to the repo, lost on a profile reset, unreviewable in a diff, and
impossible for a second person to read. So this server stages the artifact's
publishable site and puts one small JSON store behind it, writing named
documents into the artifact's own ``state/`` directory — real files, next to
the work, committed with it.

``state/`` is a sibling of ``site/``, which is the whole point of putting it
there: the deploy firewall only ever ships from the site root, so nothing a
reader saves can leak into a publish by accident.

The server is deliberately small and deliberately local. It binds to loopback,
has no authentication, and is not a deployment target. Two rules keep the
write path safe:

* document names are a strict slug — the path is built from a validated name,
  never from raw request text, so ``..`` and absolute paths cannot appear;
* the site is served from a staged copy produced by the firewall, so a private
  working file cannot be fetched even by guessing its URL.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import firewall
from .manifest import Manifest

STATE_DIR = "state"
API_ROOT = "/_artoo/state"
MAX_BODY = 4 * 1024 * 1024  # a saved view is small; anything larger is a mistake

# Slug rule for both the collection and the document name. Deliberately tight:
# these become path segments, and the cheapest way to be sure a request cannot
# escape the state directory is to refuse anything that is not obviously a name.
_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class StateStore:
    """Named JSON documents under ``<artifact>/state/<collection>/<name>.json``."""

    def __init__(self, root: Path):
        self.root = root

    def _dir(self, collection: str) -> Path:
        return self.root / collection

    def _path(self, collection: str, name: str) -> Path:
        return self._dir(collection) / f"{name}.json"

    @staticmethod
    def valid(*names: str) -> bool:
        return all(bool(_SLUG.match(n)) for n in names)

    def list(self, collection: str) -> list[dict]:
        directory = self._dir(collection)
        if not directory.is_dir():
            return []
        entries = []
        for path in sorted(directory.glob("*.json")):
            stat = path.stat()
            entries.append(
                {
                    "name": path.stem,
                    "updated": datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "bytes": stat.st_size,
                    "durable": True,
                }
            )
        return entries

    def read(self, collection: str, name: str):
        path = self._path(collection, name)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, collection: str, name: str, document) -> dict:
        directory = self._dir(collection)
        directory.mkdir(parents=True, exist_ok=True)
        path = self._path(collection, name)
        payload = {
            "name": name,
            "updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "document": document,
        }
        # Written whole, through a temporary file in the same directory, so a
        # crashed or concurrent save can never leave a half-parsed preset that
        # the page will then refuse to load.
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
        return {"name": name, "updated": payload["updated"], "durable": True, "path": str(path)}

    def delete(self, collection: str, name: str) -> bool:
        path = self._path(collection, name)
        if not path.is_file():
            return False
        path.unlink()
        return True


class _Handler(SimpleHTTPRequestHandler):
    """Static files from the staged site, plus the state API under /_artoo.

    The store and the quiet flag arrive per instance rather than as class
    attributes, so two servers in one process (which is exactly what a test
    suite does) cannot end up writing into each other's state directory.
    """

    def __init__(self, *args, store: StateStore, quiet: bool = False, **kwargs):
        self.store = store
        self.quiet = quiet
        super().__init__(*args, **kwargs)

    def log_message(self, fmt, *args):  # noqa: D102 - stdlib hook
        if not self.quiet:
            super().log_message(fmt, *args)

    # -- helpers ------------------------------------------------------------

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _route(self) -> list[str] | None:
        """The `/_artoo/state/...` path segments, or None if this is not the API."""
        path = urlparse(self.path).path
        if path != API_ROOT and not path.startswith(API_ROOT + "/"):
            return None
        rest = path[len(API_ROOT):].strip("/")
        return [unquote(p) for p in rest.split("/")] if rest else []

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError(f"body of {length} bytes exceeds the {MAX_BODY}-byte limit")
        if not length:
            return None
        return json.loads(self.rfile.read(length).decode("utf-8"))

    # -- methods ------------------------------------------------------------

    def do_GET(self):  # noqa: N802 - stdlib hook
        route = self._route()
        if route is None:
            return super().do_GET()
        if len(route) == 1:
            collection = route[0]
            if not self.store.valid(collection):
                return self._error(HTTPStatus.BAD_REQUEST, f"bad collection name {collection!r}")
            return self._json(HTTPStatus.OK, {"collection": collection, "entries": self.store.list(collection)})
        if len(route) == 2:
            collection, name = route
            if not self.store.valid(collection, name):
                return self._error(HTTPStatus.BAD_REQUEST, "bad collection or document name")
            document = self.store.read(collection, name)
            if document is None:
                return self._error(HTTPStatus.NOT_FOUND, f"no document {name!r} in {collection!r}")
            return self._json(HTTPStatus.OK, document)
        return self._error(HTTPStatus.NOT_FOUND, "unknown state route")

    def do_PUT(self):  # noqa: N802 - stdlib hook
        route = self._route()
        if route is None:
            return self._error(HTTPStatus.METHOD_NOT_ALLOWED, "PUT is only served under /_artoo/state")
        if len(route) != 2:
            return self._error(HTTPStatus.NOT_FOUND, "PUT /_artoo/state/<collection>/<name>")
        collection, name = route
        if not self.store.valid(collection, name):
            return self._error(HTTPStatus.BAD_REQUEST, "bad collection or document name")
        try:
            payload = self._body()
        except (ValueError, json.JSONDecodeError) as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        if not isinstance(payload, dict) or "document" not in payload:
            return self._error(HTTPStatus.BAD_REQUEST, "body must be {\"document\": …}")
        result = self.store.write(collection, name, payload["document"])
        if not self.quiet:
            self.log_message("saved %s", result["path"])
        return self._json(HTTPStatus.OK, result)

    def do_DELETE(self):  # noqa: N802 - stdlib hook
        route = self._route()
        if route is None or len(route) != 2:
            return self._error(HTTPStatus.NOT_FOUND, "DELETE /_artoo/state/<collection>/<name>")
        collection, name = route
        if not self.store.valid(collection, name):
            return self._error(HTTPStatus.BAD_REQUEST, "bad collection or document name")
        if not self.store.delete(collection, name):
            return self._error(HTTPStatus.NOT_FOUND, f"no document {name!r} in {collection!r}")
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()


def stage(m: Manifest, dest: Path) -> list[Path]:
    """Copy the publishable site into ``dest``.

    Serving the staged copy rather than ``site/`` itself means the server shows
    exactly what a deploy would show. A file the firewall withholds is not just
    unlisted, it is absent — so it cannot be reached by guessing its URL, and a
    page that only works because it read a private file fails here rather than
    in production.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    return firewall.stage(m, dest)


def serve(m: Manifest, host: str = "127.0.0.1", port: int = 8765, quiet: bool = False):
    """Build the server and return ``(httpd, staged_paths, state_dir, tmpdir)``.

    The caller owns the serve loop and the cleanup of ``tmpdir``; keeping that
    out of here is what lets the tests exercise a real server on a real socket
    without a subprocess.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="artoo-serve-"))
    staged = stage(m, tmpdir / "site")
    state_dir = m.dir / STATE_DIR
    handler = partial(
        _Handler,
        directory=str(tmpdir / "site"),
        store=StateStore(state_dir),
        quiet=quiet,
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    return httpd, staged, state_dir, tmpdir
