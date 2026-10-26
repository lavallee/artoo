#!/usr/bin/env python3
"""Refresh the Pele build that artoo-diagrams vendors into artifacts.

Pele releases every few days. Artifacts never feel that directly — each one
carries a hash-pinned copy and upgrades only on `artoo lib update` — but the
copy artoo ships should stay close to upstream, and refreshing it must be one
deterministic command rather than a hand-copied file nobody can audit.

    uv run python scripts/update-pele.py            # latest release on npm
    uv run python scripts/update-pele.py 1.10.1     # a specific release
    uv run python scripts/update-pele.py --check    # exit 1 if a newer one exists

The tarball is accepted only when its sha512 matches the registry's integrity
field *and* npm's SLSA provenance names a build of `obsidianmd/pele` at the
release's own tag. That second check is what rejects the unrelated `pele`
1.0.0 that squatted the name in 2020. It reads the provenance statement; it
does not verify the Sigstore signature over it (`npm audit signatures` does).

Only two files leave the tarball, read in memory and never extracted:
`dist/pele.global.js`, byte for byte, and `LICENSE`. The pin is written to
`libraries/diagrams/pele.json`; then re-run `scripts/sync-docs-site.py`.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "src" / "artoo" / "libraries" / "diagrams"
ASSETS = LIBRARY / "assets"
PIN = LIBRARY / "pele.json"

REGISTRY = "https://registry.npmjs.org/pele"
ATTESTATIONS = "https://registry.npmjs.org/-/npm/v1/attestations/pele@{version}"
REPOSITORY = "https://github.com/obsidianmd/pele"
SLSA = "https://slsa.dev/provenance/v1"
BUNDLE = "package/dist/pele.global.js"
LICENSE = "package/LICENSE"


class Refused(Exception):
    """The registry offered something this script will not vendor."""


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - fixed hosts
        return response.read()


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def integrity_of(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


def check_provenance(attestations: dict, version: str, tarball: bytes) -> None:
    """Require a SLSA statement for this exact tarball, built from upstream's tag."""
    digest = hashlib.sha512(tarball).hexdigest()
    for attestation in attestations.get("attestations", []):
        if attestation.get("predicateType") != SLSA:
            continue
        envelope = attestation.get("bundle", {}).get("dsseEnvelope", {})
        statement = json.loads(base64.b64decode(envelope.get("payload", "")))
        subjects = statement.get("subject", [])
        if not any(s.get("digest", {}).get("sha512") == digest for s in subjects):
            raise Refused(f"provenance for pele@{version} describes a different tarball")
        workflow = (
            statement.get("predicate", {})
            .get("buildDefinition", {})
            .get("externalParameters", {})
            .get("workflow", {})
        )
        if workflow.get("repository") != REPOSITORY:
            raise Refused(
                f"pele@{version} was built from {workflow.get('repository')!r}, "
                f"not {REPOSITORY}"
            )
        if workflow.get("ref") != f"refs/tags/{version}":
            raise Refused(f"pele@{version} was built from {workflow.get('ref')!r}, not its tag")
        return
    raise Refused(f"pele@{version} has no SLSA provenance; refusing an unattested build")


def read_members(tarball: bytes, version: str) -> tuple[bytes, bytes]:
    """The browser bundle and license, read without extracting anything to disk."""
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
        found = {}
        for name in (BUNDLE, LICENSE):
            member = archive.getmember(name)
            if not member.isfile():
                raise Refused(f"{name} in pele@{version} is not a regular file")
            found[name] = archive.extractfile(member).read()
    bundle = found[BUNDLE]
    header = bundle[:200].decode("utf-8", errors="replace")
    if not re.match(rf"/\*! Pele {re.escape(version)} \|", header):
        raise Refused(f"dist/pele.global.js does not announce itself as Pele {version}")
    return bundle, found[LICENSE]


def resolve(requested: str | None) -> tuple[str, dict]:
    meta = json.loads(_get(REGISTRY))
    version = requested or meta["dist-tags"]["latest"]
    if version not in meta["versions"]:
        raise Refused(f"npm has no pele@{version}")
    return version, meta["versions"][version]


def current() -> dict:
    return json.loads(PIN.read_text(encoding="utf-8")) if PIN.is_file() else {}


def update(requested: str | None) -> str:
    version, release = resolve(requested)
    tarball = _get(release["dist"]["tarball"])
    expected = release["dist"]["integrity"]
    if integrity_of(tarball) != expected:
        raise Refused(f"pele@{version} tarball does not match the registry's {expected}")
    try:
        attestations = json.loads(_get(ATTESTATIONS.format(version=version)))
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        attestations = {}
    check_provenance(attestations, version, tarball)
    bundle, license_text = read_members(tarball, version)

    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "pele.global.js").write_bytes(bundle)
    (ASSETS / "PELE-LICENSE").write_bytes(license_text)
    pin = {
        "package": "pele",
        "version": version,
        "integrity": expected,
        "bundle": "dist/pele.global.js",
        "bundle_sha256": hashlib.sha256(bundle).hexdigest(),
        "repository": REPOSITORY,
        "ref": f"refs/tags/{version}",
    }
    PIN.write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("version", nargs="?", help="exact pele release (default: latest)")
    parser.add_argument(
        "--check", action="store_true", help="report whether a newer release exists; change nothing"
    )
    args = parser.parse_args(argv)
    pinned = current().get("version", "")
    try:
        if args.check:
            latest, _ = resolve(None)
            if pinned and _version_key(latest) <= _version_key(pinned):
                print(f"pele {pinned} is current")
                return 0
            print(f"pele {latest} is available (pinned: {pinned or 'none'})")
            return 1
        version = update(args.version)
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if version == pinned:
        print(f"pele {version} re-vendored (unchanged pin)")
    else:
        print(f"pele {pinned or 'none'} → {version}")
    print("next: uv run python scripts/sync-docs-site.py && uv run pytest -q")
    return 0


if __name__ == "__main__":
    sys.exit(main())
