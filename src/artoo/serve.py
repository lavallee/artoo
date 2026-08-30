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
* every request is checked against the same firewall rule a deploy applies, so
  a private working file cannot be fetched even by guessing its URL.

Files are read live from ``site/`` rather than from a staged snapshot. A
snapshot would be the obvious way to guarantee the firewall — serve only what
was copied — but it also freezes the artifact at the moment the server
started, which makes the one command whose whole job is iteration the one
command you have to restart after every edit. Filtering per request gives the
same guarantee against the current bytes.
"""

from __future__ import annotations

import json
import re
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
    """Static files from the live site, plus the state API under /_artoo.

    The store and the quiet flag arrive per instance rather than as class
    attributes, so two servers in one process (which is exactly what a test
    suite does) cannot end up writing into each other's state directory.
    """

    def __init__(self, *args, store: StateStore, quiet: bool = False, **kwargs):
        self.store = store
        self.quiet = quiet
        self._sent_no_store = False
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

    def _withheld(self) -> bool:
        """Would the firewall refuse to publish the path being requested?

        Checked on the URL rather than on the resolved file, because the answer
        has to be the same for a path that does not exist: replying 404 for a
        missing private file and 403 for a present one would turn the firewall
        into an oracle for what the artifact is hiding.
        """
        path = unquote(urlparse(self.path).path).lstrip("/")
        if not path:
            return False
        try:
            return not firewall.is_publishable(Path(path))
        except (ValueError, OSError):
            return True

    def end_headers(self):  # noqa: D102 - stdlib hook
        """Never let a browser cache a file from this server.

        Reading live from `site/` only helps if the browser asks. Without this
        an edited stylesheet keeps rendering from cache, and the failure looks
        like the edit not working rather than like the file not being fetched —
        which costs more time than the caching ever saves on a loopback server.
        """
        if not self._sent_no_store:
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self._sent_no_store = True
        super().end_headers()

    def send_response(self, *args, **kwargs):  # noqa: D102 - stdlib hook
        self._sent_no_store = False
        return super().send_response(*args, **kwargs)

    def do_GET(self):  # noqa: N802 - stdlib hook
        route = self._route()
        if route is None:
            if self._withheld():
                self.send_error(HTTPStatus.NOT_FOUND, "File not found")
                return None
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

    def do_HEAD(self):  # noqa: N802 - stdlib hook
        if self._route() is None and self._withheld():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None
        return super().do_HEAD()

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


def serve(m: Manifest, host: str = "127.0.0.1", port: int = 8765, quiet: bool = False):
    """Build the server and return ``(httpd, publishable_paths, state_dir)``.

    The caller owns the serve loop. Keeping it out of here is what lets the
    tests exercise a real server on a real socket without a subprocess.

    ``publishable_paths`` is a count taken once, for the startup line; the
    firewall itself is applied per request, so a file added after the server
    started is served, and one added under a `_` path still is not.
    """
    state_dir = m.dir / STATE_DIR
    handler = partial(
        _Handler,
        directory=str(m.site_dir),
        store=StateStore(state_dir),
        quiet=quiet,
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    return httpd, list(firewall.iter_publishable(m.site_dir)), state_dir
