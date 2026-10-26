"""scripts/update-pele.py: the refusals that keep a wrong Pele out of artoo."""

import base64
import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "update-pele.py"
spec = importlib.util.spec_from_file_location("update_pele", SCRIPT)
update_pele = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update_pele)


def _tarball(bundle: bytes, license_text: bytes = b"MIT License\n") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in ((update_pele.BUNDLE, bundle), (update_pele.LICENSE, license_text)):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _attestations(tarball: bytes, repository: str, ref: str) -> dict:
    statement = {
        "subject": [{"digest": {"sha512": hashlib.sha512(tarball).hexdigest()}}],
        "predicate": {
            "buildDefinition": {
                "externalParameters": {"workflow": {"repository": repository, "ref": ref}}
            }
        },
    }
    payload = base64.b64encode(json.dumps(statement).encode()).decode()
    return {
        "attestations": [
            {"predicateType": update_pele.SLSA, "bundle": {"dsseEnvelope": {"payload": payload}}}
        ]
    }


def test_accepts_upstream_build_of_its_own_tag():
    tarball = _tarball(b"/*! Pele 2.0.0 | MIT License */")
    attestations = _attestations(tarball, update_pele.REPOSITORY, "refs/tags/2.0.0")
    update_pele.check_provenance(attestations, "2.0.0", tarball)
    bundle, license_text = update_pele.read_members(tarball, "2.0.0")
    assert bundle.startswith(b"/*! Pele 2.0.0 |")
    assert license_text.startswith(b"MIT")


@pytest.mark.parametrize(
    ("repository", "ref", "reason"),
    [
        ("https://github.com/someone/pele", "refs/tags/2.0.0", "built from"),
        (update_pele.REPOSITORY, "refs/heads/main", "not its tag"),
    ],
)
def test_refuses_builds_from_elsewhere(repository, ref, reason):
    tarball = _tarball(b"/*! Pele 2.0.0 | */")
    with pytest.raises(update_pele.Refused, match=reason):
        update_pele.check_provenance(_attestations(tarball, repository, ref), "2.0.0", tarball)


def test_refuses_unattested_and_mismatched_tarballs():
    tarball = _tarball(b"/*! Pele 2.0.0 | */")
    with pytest.raises(update_pele.Refused, match="no SLSA provenance"):
        update_pele.check_provenance({}, "2.0.0", tarball)
    other = _attestations(_tarball(b"other"), update_pele.REPOSITORY, "refs/tags/2.0.0")
    with pytest.raises(update_pele.Refused, match="different tarball"):
        update_pele.check_provenance(other, "2.0.0", tarball)


def test_refuses_a_bundle_that_is_not_the_requested_release():
    with pytest.raises(update_pele.Refused, match="Pele 2.0.0"):
        update_pele.read_members(_tarball(b"/*! Pele 1.9.0 | */"), "2.0.0")


def test_integrity_matches_npm_format():
    assert update_pele.integrity_of(b"x").startswith("sha512-")
