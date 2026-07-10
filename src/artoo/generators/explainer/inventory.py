"""Deterministic repo inventory — the explainer's ground truth.

No models here. Everything a page later asserts about size, layout, or
history traces back to this pass, cached as ``work/inventory.json``.
"""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from collections import defaultdict
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".ruff_cache", "dist", "build", ".artoo", ".tox",
    "target", ".next", ".cache",
}

CODE_EXTENSIONS = {
    ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".rs", ".go", ".rb",
    ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cs", ".swift", ".sh",
    ".sql", ".css", ".html", ".toml", ".yaml", ".yml", ".json", ".md",
}

TEXT_CAP = 2_000_000  # skip files larger than this when counting lines

UNIT_TARGET_LOC = 6_000  # split a unit bigger than this by subdirectory
MAX_UNITS = 24


def _run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _count_lines(path: Path) -> int:
    try:
        if path.stat().st_size > TEXT_CAP:
            return 0
        return path.read_bytes().count(b"\n")
    except OSError:
        return 0


def _iter_files(repo: Path):
    stack = [repo]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except (PermissionError, FileNotFoundError):
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in SKIP_DIRS:
                    stack.append(entry)
            elif entry.is_file():
                yield entry


def _python_packages(repo: Path, files: list[Path]) -> list[dict]:
    """Parse every pyproject.toml: names, deps, scripts, workspace shape."""
    packages = []
    for path in files:
        if path.name != "pyproject.toml":
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        project = data.get("project", {})
        packages.append(
            {
                "path": str(path.parent.relative_to(repo)) or ".",
                "name": project.get("name", ""),
                "description": project.get("description", ""),
                "dependencies": project.get("dependencies", []),
                "scripts": sorted(project.get("scripts", {})),
                "workspace_members": data.get("tool", {})
                .get("uv", {})
                .get("workspace", {})
                .get("members", []),
            }
        )
    return packages


_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", re.MULTILINE)


def _python_modules(repo: Path, files: list[Path]) -> list[dict]:
    modules = []
    for path in files:
        if path.suffix != ".py":
            continue
        rel = path.relative_to(repo)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        doc = ""
        stripped = text.lstrip()
        for quote in ('"""', "'''"):
            if stripped.startswith(quote):
                end = stripped.find(quote, 3)
                if end > 0:
                    doc = stripped[3:end].strip().splitlines()[0] if stripped[3:end].strip() else ""
                break
        modules.append(
            {
                "path": str(rel),
                "loc": text.count("\n"),
                "doc": doc,
                "imports": sorted({m.split(".")[0] for m in _IMPORT_RE.findall(text)}),
                "is_test": path.name.startswith("test_") or "tests" in rel.parts,
            }
        )
    return modules


def _readme_summary(repo: Path) -> dict:
    for name in ("README.md", "README.rst", "README"):
        path = repo / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        title = next((ln.lstrip("# ").strip() for ln in lines if ln.startswith("#")), "")
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip() and not p.lstrip().startswith(("#", "[!", "<", "```"))]
        return {
            "file": name,
            "title": title,
            "first_paragraph": paragraphs[0][:600] if paragraphs else "",
        }
    return {}


def analysis_units(inv: dict) -> list[dict]:
    """Group source files into analysis units for the model fan-out.

    Unit = a top-level directory (or ``root``); oversized units split one
    level down. Docs/tests are kept but tagged so prompts can weight them.
    """
    loc_by_path = {f["path"]: f["loc"] for f in inv["files"]}
    by_dir: dict[str, dict] = defaultdict(lambda: {"loc": 0, "files": []})
    for f in inv["files"]:
        rel = Path(f["path"])
        if rel.suffix not in CODE_EXTENSIONS:
            continue
        top = rel.parts[0] if len(rel.parts) > 1 else "root"
        by_dir[top]["loc"] += f["loc"]
        by_dir[top]["files"].append(f["path"])

    units = []
    for name, info in sorted(by_dir.items()):
        if info["loc"] > UNIT_TARGET_LOC and name != "root":
            sub: dict[str, dict] = defaultdict(lambda: {"loc": 0, "files": []})
            for fp in info["files"]:
                parts = Path(fp).parts
                key = f"{name}/{parts[1]}" if len(parts) > 2 else name
                sub[key]["loc"] += loc_by_path.get(fp, 0)
                sub[key]["files"].append(fp)
            for sub_name, sub_info in sorted(sub.items()):
                units.append({"name": sub_name, **sub_info})
        else:
            units.append({"name": name, **info})

    units.sort(key=lambda u: -u["loc"])
    if len(units) > MAX_UNITS:
        heads, tail = units[: MAX_UNITS - 1], units[MAX_UNITS - 1 :]
        merged = {
            "name": "misc",
            "loc": sum(u["loc"] for u in tail),
            "files": [fp for u in tail for fp in u["files"]],
        }
        units = heads + [merged]
    return [u for u in units if u["files"]]


def take_inventory(repo: Path, *, exclude: tuple[str, ...] = ()) -> dict:
    """``exclude``: repo-relative path prefixes to skip (e.g. the artifact's
    own directory, so an explainer never inventories itself)."""
    repo = repo.resolve()
    files = [
        f
        for f in _iter_files(repo)
        if not any(str(f.relative_to(repo)).startswith(prefix) for prefix in exclude)
    ]

    file_rows = []
    ext_loc: dict[str, int] = defaultdict(int)
    for path in files:
        rel = path.relative_to(repo)
        loc = _count_lines(path) if path.suffix in CODE_EXTENSIONS else 0
        file_rows.append({"path": str(rel), "loc": loc})
        if loc:
            ext_loc[path.suffix] += loc

    modules = _python_modules(repo, files)
    inv = {
        "repo": str(repo),
        "name": repo.name,
        "git": {
            "head": _run_git(repo, "rev-parse", "--short", "HEAD"),
            "commits": int(_run_git(repo, "rev-list", "--count", "HEAD") or 0),
            "first_commit": _run_git(repo, "log", "--reverse", "--format=%as", "-1"),
            "last_commit": _run_git(repo, "log", "-1", "--format=%as"),
            "remote": _run_git(repo, "remote", "get-url", "origin"),
        },
        "loc_by_extension": dict(sorted(ext_loc.items(), key=lambda kv: -kv[1])),
        "files": file_rows,
        "python": {
            "packages": _python_packages(repo, files),
            "modules": modules,
            "source_loc": sum(m["loc"] for m in modules if not m["is_test"]),
            "test_loc": sum(m["loc"] for m in modules if m["is_test"]),
            "test_files": sum(1 for m in modules if m["is_test"]),
        },
        "readme": _readme_summary(repo),
        "docs": sorted(
            str(p.relative_to(repo))
            for p in files
            if p.suffix == ".md" and p.parts[len(repo.parts)] in ("docs",)
        ),
    }
    return inv


def load_or_take(
    repo: Path, work: Path, *, fresh: bool = False, exclude: tuple[str, ...] = ()
) -> dict:
    cache = work / "inventory.json"
    if cache.is_file() and not fresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    inv = take_inventory(repo, exclude=exclude)
    work.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(inv, indent=1), encoding="utf-8")
    return inv
