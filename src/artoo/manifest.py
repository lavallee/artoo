"""The artifact manifest: ``artifact.toml`` load, validate, and stable write.

The manifest is the source of truth for an artifact. Everything else —
listings, deploy routing, library provenance — derives from it. Writes are
deterministic (fixed key order, scalars before tables) so manifests diff
cleanly in git.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

MANIFEST_NAME = "artifact.toml"

KINDS = [
    "explainer",
    "report",
    "reference-guide",
    "research-review",
    "walkthrough",
    "case-study",
    "explorer",
    "note",
]

STATUSES = ["draft", "building", "live", "archived"]


@dataclass
class Manifest:
    slug: str
    title: str
    description: str = ""
    kind: str = "report"
    status: str = "draft"
    created: str = ""
    updated: str = ""

    build_commands: list[str] = field(default_factory=list)
    site: str = "site"
    notebook: str = ""

    deploy_target: str = ""
    deploy_config: dict = field(default_factory=dict)

    workers: dict = field(default_factory=dict)
    libraries: list[dict] = field(default_factory=list)
    vendor: list[dict] = field(default_factory=list)

    # Set on load; not serialized.
    path: Path | None = None

    @property
    def dir(self) -> Path:
        if self.path is None:
            raise ValueError("manifest has no path (not loaded from disk)")
        return self.path.parent

    @property
    def site_dir(self) -> Path:
        return self.dir / self.site

    @property
    def notebook_dir(self) -> Path | None:
        return self.dir / self.notebook if self.notebook else None

    def validate(self) -> list[str]:
        problems = []
        if not self.slug:
            problems.append("artifact.slug is required")
        elif not all(c.isalnum() or c in "-_" for c in self.slug):
            problems.append(f"artifact.slug {self.slug!r} may only contain [a-zA-Z0-9-_]")
        if not self.title:
            problems.append("artifact.title is required")
        if self.kind not in KINDS:
            problems.append(f"artifact.kind {self.kind!r} not one of {', '.join(KINDS)}")
        if self.status not in STATUSES:
            problems.append(f"artifact.status {self.status!r} not one of {', '.join(STATUSES)}")
        if ".." in self.site or Path(self.site).is_absolute():
            problems.append("build.site must be a relative path inside the artifact")
        if self.notebook and (".." in self.notebook or Path(self.notebook).is_absolute()):
            problems.append("research.notebook must be a relative path inside the artifact")
        if self.notebook:
            site = Path(self.site)
            nb = Path(self.notebook)
            if nb == site or site in nb.parents or nb in site.parents:
                problems.append("research.notebook must not overlap build.site")
        for lib in self.libraries:
            if "name" not in lib:
                problems.append("[[libraries]] entry missing name")
        for v in self.vendor:
            for key in ("name", "url", "path"):
                if key not in v:
                    problems.append(f"[[vendor]] entry missing {key}")
        return problems

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path
        if target is None:
            raise ValueError("no path to save manifest to")
        if target.is_dir():
            target = target / MANIFEST_NAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dumps(self), encoding="utf-8")
        self.path = target
        return target


def _toml_str(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return _toml_str(str(value))


def _table(name: str, pairs: list[tuple[str, object]]) -> str:
    lines = [f"[{name}]"]
    for key, value in pairs:
        lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def dumps(m: Manifest) -> str:
    """Serialize with stable ordering: scalars before tables, fixed key order."""
    blocks = []

    artifact_pairs: list[tuple[str, object]] = [("slug", m.slug), ("title", m.title)]
    if m.description:
        artifact_pairs.append(("description", m.description))
    artifact_pairs.append(("kind", m.kind))
    artifact_pairs.append(("status", m.status))
    if m.created:
        artifact_pairs.append(("created", m.created))
    if m.updated:
        artifact_pairs.append(("updated", m.updated))
    blocks.append(_table("artifact", artifact_pairs))

    build_pairs: list[tuple[str, object]] = []
    if m.build_commands:
        build_pairs.append(("commands", m.build_commands))
    if m.site != "site":
        build_pairs.append(("site", m.site))
    if build_pairs:
        blocks.append(_table("build", build_pairs))

    if m.notebook:
        blocks.append(_table("research", [("notebook", m.notebook)]))

    if m.workers:
        blocks.append(_table("workers", sorted(m.workers.items())))

    if m.deploy_target:
        blocks.append(_table("deploy", [("target", m.deploy_target)]))
        if m.deploy_config:
            blocks.append(
                _table(f"deploy.{m.deploy_target}", sorted(m.deploy_config.items()))
            )

    for lib in m.libraries:
        pairs = [(k, lib[k]) for k in ("name", "version", "sha256", "path") if k in lib]
        blocks.append("[[libraries]]\n" + "\n".join(f"{k} = {_toml_value(v)}" for k, v in pairs) + "\n")

    for v in m.vendor:
        pairs = [(k, v[k]) for k in ("name", "url", "sha256", "path") if k in v]
        blocks.append("[[vendor]]\n" + "\n".join(f"{k} = {_toml_value(val)}" for k, val in pairs) + "\n")

    return "\n".join(blocks)


def loads(text: str) -> Manifest:
    data = tomllib.loads(text)
    artifact = data.get("artifact", {})
    build = data.get("build", {})
    research = data.get("research", {})
    deploy = data.get("deploy", {})
    target = deploy.get("target", "")
    deploy_config = deploy.get(target, {}) if target else {}

    return Manifest(
        slug=artifact.get("slug", ""),
        title=artifact.get("title", ""),
        description=artifact.get("description", ""),
        kind=artifact.get("kind", "report"),
        status=artifact.get("status", "draft"),
        created=str(artifact.get("created", "")),
        updated=str(artifact.get("updated", "")),
        build_commands=list(build.get("commands", [])),
        site=build.get("site", "site"),
        notebook=research.get("notebook", ""),
        deploy_target=target,
        deploy_config=dict(deploy_config),
        workers=dict(data.get("workers", {})),
        libraries=[dict(x) for x in data.get("libraries", [])],
        vendor=[dict(x) for x in data.get("vendor", [])],
    )


def load(path: Path) -> Manifest:
    """Load a manifest from an artifact dir or a direct path to artifact.toml."""
    if path.is_dir():
        path = path / MANIFEST_NAME
    if not path.is_file():
        raise FileNotFoundError(f"no {MANIFEST_NAME} at {path}")
    m = loads(path.read_text(encoding="utf-8"))
    m.path = path.resolve()
    return m


def new(slug: str, title: str, kind: str = "report", description: str = "") -> Manifest:
    return Manifest(
        slug=slug,
        title=title,
        description=description,
        kind=kind,
        status="draft",
        created=date.today().isoformat(),
    )
