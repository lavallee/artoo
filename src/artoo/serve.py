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
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import firewall
from .manifest import Manifest

from .state import MAX_BODY, STATE_DIR, STATE_PROTOCOL, StateError, StateStore, strict_json

API_ROOT = "/_artoo/state"


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
        if self.headers.get("Transfer-Encoding"):
            raise StateError("Transfer-Encoding is not supported")
        if self.headers.get_content_type() != "application/json":
            raise StateError("writes require application/json", 415, "content_type")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isdigit():
            raise StateError("one positive Content-Length is required")
        length = int(lengths[0])
        if not 0 < length <= MAX_BODY:
            raise StateError("request body exceeds size limit", 413, "too_large")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise StateError("incomplete request body")
        try:
            return strict_json(raw)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise StateError("invalid JSON body") from exc

    def _trusted_request(self):
        host = self.headers.get("Host", "")
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        bound = self.server.server_address[0]
        if bound not in ("0.0.0.0", "::"):
            allowed.add(f"{bound}:{port}")
        origin = self.headers.get("Origin")
        if (host not in allowed or (origin and origin != "http://" + host)
                or self.headers.get("Sec-Fetch-Site") == "cross-site"):
            raise StateError("state API requires a same-origin local request", 403, "origin")

    def _state_request(self, method):
        try:
            self._trusted_request()
            route = self._route()
            if route is None or len(route) not in (1, 2):
                raise StateError("unknown state route", 404, "not_found")
            collection = route[0]
            if method == "GET" and len(route) == 1:
                return self._json(200, {"collection": collection, "protocol": STATE_PROTOCOL,
                                        "durable": True, "entries": self.store.list(collection)})
            if len(route) != 2:
                raise StateError("document name required", 404, "not_found")
            name = route[1]
            if method == "GET":
                doc = self.store.read(collection, name)
                if doc is None:
                    raise StateError("document not found", 404, "not_found")
                return self._json(200, doc)
            payload = self._body()
            if not isinstance(payload, dict) or "expected_revision" not in payload:
                raise StateError("expected_revision is required (null to create)", 428, "precondition")
            if method == "PUT":
                if "document" not in payload:
                    raise StateError("document is required")
                result = self.store.write(collection, name, payload["document"],
                                          expected_revision=payload["expected_revision"])
                return self._json(200, result)
            deleted = self.store.delete(collection, name,
                                        expected_revision=payload["expected_revision"])
            if not deleted:
                raise StateError("document not found", 404, "not_found")
            self.send_response(204)
            self.end_headers()
        except StateError as exc:
            return self._json(exc.status, exc.as_dict())

    # -- methods ------------------------------------------------------------

    def _withheld(self) -> bool:
        """Would the firewall refuse to publish the path being requested?

        Checked on the URL rather than on the resolved file, because the answer
        has to be the same for a path that does not exist: replying 404 for a
        missing private file and 403 for a present one would turn the firewall
        into an oracle for what the artifact is hiding.
        """
        path = unquote(urlparse(self.path).path).lstrip("/")
        try:
            site = Path(self.directory).resolve()
            target = (site / path).resolve()
            if target != site and site not in target.parents:
                return True
            if target.is_dir():
                for index in ("index.html", "index.htm"):
                    candidate = target / index
                    if candidate.exists():
                        resolved = candidate.resolve()
                        if resolved != site and site not in resolved.parents:
                            return True
                        break
            return bool(path) and not firewall.is_publishable(Path(path))
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
        return self._state_request("GET")

    def do_HEAD(self):  # noqa: N802 - stdlib hook
        if self._route() is None and self._withheld():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None
        return super().do_HEAD()

    def do_PUT(self):  # noqa: N802 - stdlib hook
        return self._state_request("PUT")

    def do_DELETE(self):  # noqa: N802 - stdlib hook
        return self._state_request("DELETE")


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
        store=StateStore.for_artifact(m.dir, m.site_dir, m.state_collections),
        quiet=quiet,
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    return httpd, list(firewall.iter_publishable(m.site_dir)), state_dir
