"""Build an artifact: run its refresh commands, then verify the site."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import date

from . import content as content_mod, data as data_mod, firewall
from . import libraries as libraries_mod
from . import provenance as provenance_mod
from . import verify as verify_mod
from .manifest import Manifest


@dataclass
class BuildResult:
    ok: bool
    ran: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated: list[str] = field(default_factory=list)
    withheld: list[str] = field(default_factory=list)
    stamped: str = ""  # the `updated` date written back, if any
    provenance: str = ""  # one-line note on the provenance projection, if any


def build(m: Manifest, *, dry_run: bool = False) -> BuildResult:
    """Run ``[build] commands`` from the artifact directory, then firewall-check.

    Build commands refresh generated inputs (exports, data snapshots). They
    run with the artifact directory as cwd so relative paths in the manifest
    stay portable.
    """
    result = BuildResult(ok=True)
    result.problems.extend(m.validate())
    if result.problems:
        result.ok = False
        return result
    for command in m.build_commands:
        result.ran.append(command)
        if dry_run:
            continue
        proc = subprocess.run(
            command, shell=True, cwd=m.dir, capture_output=True, text=True
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            result.ok = False
            result.problems.append(
                f"build command failed ({proc.returncode}): {command}\n{detail}"
            )
            return result

    packed = data_mod.pack(m, dry_run=dry_run)
    result.generated.extend(str(path.relative_to(m.dir)) for path in packed.written)
    result.problems.extend(packed.problems)

    # Declared neutral evidence is a hard input. Flip remains an optional
    # adapter: no Flip, no notebook, or a policy refusal is only a note.
    if not dry_run:
        prov = provenance_mod.ingest(m)
        if prov.status == "written":
            c = prov.counts
            origin = (
                f"evidence {m.evidence_source}"
                if m.evidence_source
                else f"notebook {prov.vintage.get('uid') or '?'}"
            )
            result.provenance = (
                f"provenance.json ← {origin} "
                f"({c.get('sources', 0)} sources, {c.get('claims', 0)} claims)"
            )
        elif prov.status == "error":
            result.provenance = f"provenance skipped: {prov.note}"
            if m.evidence_source:
                result.problems.append(prov.note)
    else:
        result.provenance = "provenance projection skipped (dry run)"

    rendered = content_mod.render(m, dry_run=dry_run)
    result.generated.extend(str(path.relative_to(m.dir)) for path in rendered.written)
    result.problems.extend(rendered.problems)

    result.problems.extend(firewall.check(m))
    if m.site_dir.is_dir():
        result.problems.extend(provenance_mod.data_json_problems(m.site_dir))
        # A class invented inside a library's namespace renders as nothing at
        # all — the page loads, the layout is silently wrong, and the failure
        # surfaces as "the CSS is broken" much later. Catching it here is what
        # makes the vocabulary in ARTOO_REFERENCE.md worth trusting: guess, and the
        # build tells you immediately which real class you meant.
        result.problems.extend(f.message() for f in libraries_mod.markup_check(m))
        verification = verify_mod.static(m)
        result.problems.extend(verification.problems)
        result.warnings.extend(verification.warnings)
    if result.problems:
        result.ok = False
    result.withheld = [str(p) for p in firewall.withheld(m.site_dir)] if m.site_dir.is_dir() else []

    # A successful build is the moment the site last changed, so stamp
    # `updated` here. Without this the field is declared but never written,
    # and every consumer that sorts or displays freshness has to fall back to
    # file mtimes. Only on a real, successful build: a dry run touches
    # nothing, and a failed build did not produce a new site.
    if result.ok and not dry_run and m.path is not None:
        today = date.today().isoformat()
        if m.updated != today:
            prior_updated = m.updated
            m.updated = today
            refreshed = content_mod.render(m)
            if refreshed.problems:
                m.updated = prior_updated
                result.ok = False
                result.problems.extend(refreshed.problems)
                return result
            m.save()
            result.stamped = today

    return result
