"""`artoo serve` — the staged site, and the state store behind it.

These run a real server on a real socket. The state API's whole job is to turn
a reader's configuration into a file on disk, so testing it against a mock
would test the mock; and the firewall guarantee ("a private file is absent,
not merely unlinked") is only true of an actual HTTP fetch.
"""

import json
import shutil
import threading
import urllib.error
import urllib.request

import pytest

from artoo import serve as serve_mod


@pytest.fixture
def server(artifact):
    """A running server for a scaffolded artifact, on an OS-assigned port."""
    httpd, staged, state_dir, tmpdir = serve_mod.serve(artifact, port=0, quiet=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield {
            "url": f"http://{host}:{port}",
            "staged": staged,
            "state_dir": state_dir,
            "artifact": artifact,
        }
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        shutil.rmtree(tmpdir, ignore_errors=True)


def request(url, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as res:
        body = res.read()
        return res.status, (json.loads(body) if body else None)


def test_the_site_is_served(server):
    status, _ = 0, None
    with urllib.request.urlopen(server["url"] + "/index.html", timeout=5) as res:
        status = res.status
        body = res.read().decode()
    assert status == 200
    assert "<html" in body.lower()


def test_a_withheld_file_is_absent_rather_than_unlinked(server):
    """The server shows what a deploy would show, so an underscore path 404s.

    A page that only works because it reached a private working file has to
    fail here — the alternative is discovering it after publication, when the
    file either shipped or the page broke.
    """
    site = server["artifact"].site_dir
    (site / "_private.json").write_text('{"secret": true}')
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(server["url"] + "/_private.json", timeout=5)
    assert exc.value.code == 404


def test_a_saved_document_becomes_a_file_on_disk(server):
    status, result = request(
        server["url"] + "/_artoo/state/presets/means-heavy",
        method="PUT",
        payload={"document": {"weights": {"income": 0.6, "levy": 0.4}}},
    )
    assert status == 200
    assert result["durable"] is True

    path = server["state_dir"] / "presets" / "means-heavy.json"
    assert path.is_file()
    written = json.loads(path.read_text())
    assert written["document"]["weights"]["income"] == 0.6
    assert written["name"] == "means-heavy"

    # state/ is a sibling of site/, which is what keeps it out of any deploy.
    assert server["state_dir"].parent == server["artifact"].dir
    assert "state" not in {p.parts[0] for p in server["staged"]}


def test_roundtrip_list_load_and_delete(server):
    base = server["url"] + "/_artoo/state/presets"
    request(base + "/a", method="PUT", payload={"document": [1, 2, 3]})
    request(base + "/b", method="PUT", payload={"document": {"k": "v"}})

    _, listing = request(base)
    assert [e["name"] for e in listing["entries"]] == ["a", "b"]
    assert all(e["updated"].endswith("Z") for e in listing["entries"])

    _, doc = request(base + "/a")
    assert doc["document"] == [1, 2, 3]

    status, _ = request(base + "/a", method="DELETE")
    assert status == 204
    _, listing = request(base)
    assert [e["name"] for e in listing["entries"]] == ["b"]


def test_an_empty_collection_lists_rather_than_errors(server):
    """A page asking for its presets before any exist gets [], not a 404.

    The probe in ArtooStore uses this call to decide whether saves are durable,
    so an empty store has to answer successfully or every first run reports
    itself as browser-only.
    """
    status, listing = request(server["url"] + "/_artoo/state/presets")
    assert status == 200
    assert listing["entries"] == []


@pytest.mark.parametrize("name", ["../escape", "..", "a/b", "", "with space", "x" * 65])
def test_a_document_name_that_is_not_a_slug_is_refused(server, name):
    """The path is built from a validated name, so traversal never reaches disk."""
    from urllib.parse import quote

    url = server["url"] + "/_artoo/state/presets/" + quote(name, safe="")
    with pytest.raises(urllib.error.HTTPError) as exc:
        request(url, method="PUT", payload={"document": {}})
    assert exc.value.code in (400, 404)


def test_a_body_without_a_document_key_is_refused(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        request(
            server["url"] + "/_artoo/state/presets/x",
            method="PUT",
            payload={"weights": {}},
        )
    assert exc.value.code == 400


def test_loading_a_document_that_was_never_saved_is_a_404(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        request(server["url"] + "/_artoo/state/presets/never-saved")
    assert exc.value.code == 404


def test_a_save_replaces_rather_than_appends(server):
    base = server["url"] + "/_artoo/state/presets/v"
    request(base, method="PUT", payload={"document": {"n": 1}})
    request(base, method="PUT", payload={"document": {"n": 2}})
    _, doc = request(base)
    assert doc["document"] == {"n": 2}
    files = list((server["state_dir"] / "presets").iterdir())
    assert [f.name for f in files] == ["v.json"], "the atomic write left a temp file behind"
