"""Renderer-neutral code graphs and bounded interrogation views.

The graph is an evidence contract, not an architecture oracle. Deterministic
analyzers may emit ``static`` facts, imported traces may emit ``runtime``
facts, authored models may emit ``declared`` facts, and model enrichment may
only emit ``inferred`` facts. Renderers consume those labels; they never get to
upgrade one kind of truth into another.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import subprocess
import sys
import tomllib
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTRACT = "artoo-codegraph/1"
VIEW_CONTRACT = "artoo-codegraph-view/1"
TRUTH_CLASSES = {"declared", "static", "runtime", "inferred"}
NODE_KINDS = {
    "repository",
    "package",
    "module",
    "class",
    "function",
    "entrypoint",
    "external",
    "service",
    "datastore",
}
EDGE_KINDS = {
    "contains",
    "imports",
    "calls",
    "invokes",
    "depends_on",
    "reads",
    "writes",
    "sends",
    "receives",
    "declares",
    "relates",
}
DIRECTIONS = {"incoming", "outgoing", "both"}
SKIP_DIRS = {
    ".git",
    ".hg",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".artoo",
    ".tox",
    "target",
    ".next",
    ".cache",
}
LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".rb": "ruby",
    ".java": "java",
    ".kt": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".sh": "shell",
    ".sql": "sql",
}


class CodeGraphError(ValueError):
    """An invalid graph, reference, or interrogation request."""


@dataclass
class _Symbol:
    id: str
    name: str
    qualified_name: str
    kind: str
    node: ast.AST
    class_name: str = ""


@dataclass
class _Module:
    path: str
    name: str
    id: str
    tree: ast.Module
    symbols: list[_Symbol]
    is_package: bool


def schema_path() -> Path:
    """The bundled JSON Schema for external analyzer authors."""
    return Path(__file__).parent / "schema" / "codegraph-v1.json"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _relative(path: Path, repo: Path) -> str:
    return path.relative_to(repo).as_posix()


def _excluded(rel: str, exclude: tuple[str, ...]) -> bool:
    normalized = tuple(prefix.rstrip("/") + "/" for prefix in exclude)
    return any(rel == prefix.rstrip("/") or rel.startswith(prefix) for prefix in normalized)


def _code_files(repo: Path, exclude: tuple[str, ...]) -> list[Path]:
    found = []
    stack = [repo]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), reverse=True)
        except (FileNotFoundError, PermissionError):
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            rel = _relative(entry, repo)
            if _excluded(rel, exclude):
                continue
            if entry.is_dir():
                if entry.name not in SKIP_DIRS:
                    stack.append(entry)
            elif entry.is_file() and entry.suffix.lower() in LANGUAGES:
                found.append(entry)
    return sorted(found)


def _module_name(rel: Path) -> str:
    parts = list(rel.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts.pop(0)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or rel.parent.name or rel.stem


def _node_id(kind: str, coordinate: str) -> str:
    return f"{kind}:{coordinate}"


def _edge_id(kind: str, source: str, target: str, path: str, line: int) -> str:
    value = "\0".join((kind, source, target, path, str(line))).encode()
    return f"edge:{hashlib.sha256(value).hexdigest()[:20]}"


def _evidence(path: str, line: int, kind: str, note: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {"path": path, "line": max(1, line), "kind": kind}
    if note:
        row["note"] = note
    return row


def _symbol_rows(module: _Module) -> list[_Symbol]:
    rows = []
    for item in module.tree.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualified = f"{module.name}.{item.name}" if module.name else item.name
            rows.append(
                _Symbol(
                    id=_node_id("symbol", f"{module.path}:{item.name}"),
                    name=item.name,
                    qualified_name=qualified,
                    kind="function",
                    node=item,
                )
            )
        elif isinstance(item, ast.ClassDef):
            qualified = f"{module.name}.{item.name}" if module.name else item.name
            rows.append(
                _Symbol(
                    id=_node_id("symbol", f"{module.path}:{item.name}"),
                    name=item.name,
                    qualified_name=qualified,
                    kind="class",
                    node=item,
                )
            )
            for child in item.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_name = f"{item.name}.{child.name}"
                    rows.append(
                        _Symbol(
                            id=_node_id("symbol", f"{module.path}:{method_name}"),
                            name=child.name,
                            qualified_name=f"{qualified}.{child.name}",
                            kind="function",
                            node=child,
                            class_name=item.name,
                        )
                    )
    return rows


def _symbol_attributes(symbol: _Symbol) -> dict[str, str]:
    attributes = {
        "qualified_name": symbol.qualified_name,
        "visibility": "private" if symbol.name.startswith("_") else "public",
    }
    if isinstance(symbol.node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        try:
            arguments = ast.unparse(symbol.node.args)
        except Exception:
            arguments = "…"
        prefix = "async def" if isinstance(symbol.node, ast.AsyncFunctionDef) else "def"
        attributes["signature"] = f"{prefix} {symbol.name}({arguments})"
    elif isinstance(symbol.node, ast.ClassDef):
        try:
            bases = ", ".join(ast.unparse(base) for base in symbol.node.bases)
        except Exception:
            bases = ""
        attributes["signature"] = f"class {symbol.name}({bases})" if bases else f"class {symbol.name}"
    doc = ast.get_docstring(symbol.node, clean=True)
    if doc:
        attributes["doc"] = doc.splitlines()[0][:240]
    return attributes


class _Calls(ast.NodeVisitor):
    """Collect calls in one symbol without attributing nested definitions to it."""

    def __init__(self, root: ast.AST):
        self.root = root
        self.calls: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - ast visitor API
        self.calls.append(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        if node is self.root:
            self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        if node is self.root:
            self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        if node is self.root:
            self.generic_visit(node)


def _add_node(nodes: dict[str, dict], row: dict) -> None:
    existing = nodes.get(row["id"])
    if existing is None:
        nodes[row["id"]] = row
        return
    if existing.get("truth") == "declared" and row.get("truth") == "static":
        existing["truth"] = "static"
        existing.setdefault("attributes", {})["also_declared"] = True


def _add_edge(edges: dict[str, dict], row: dict) -> None:
    edges.setdefault(row["id"], row)


def _external_node(nodes: dict[str, dict], name: str, truth: str) -> str:
    top = name.split(".", 1)[0]
    node_id = _node_id("external", top.lower())
    scope = "stdlib" if top in sys.stdlib_module_names else "third_party"
    _add_node(
        nodes,
        {
            "id": node_id,
            "kind": "external",
            "label": top,
            "truth": truth,
            "attributes": {"scope": scope},
            "evidence": [],
        },
    )
    return node_id


def _resolve_relative(module: _Module, imported: ast.ImportFrom) -> str:
    if not imported.level:
        return imported.module or ""
    package = module.name if module.is_package else module.name.rpartition(".")[0]
    parts = package.split(".") if package else []
    climb = max(0, imported.level - 1)
    if climb:
        parts = parts[: max(0, len(parts) - climb)]
    if imported.module:
        parts.extend(imported.module.split("."))
    return ".".join(part for part in parts if part)


def _dependency_name(requirement: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9_.-]*)", requirement)
    return match.group(1) if match else ""


def _declared_dependencies(
    repo: Path,
    nodes: dict[str, dict],
    edges: dict[str, dict],
    package_by_dir: dict[str, str],
) -> list[tuple[str, str, str]]:
    """Add package dependencies and return declared script targets."""
    scripts = []
    for path in sorted(repo.rglob("pyproject.toml")):
        if any(part in SKIP_DIRS for part in path.relative_to(repo).parts):
            continue
        rel = _relative(path, repo)
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        project = data.get("project", {})
        parent = path.parent.relative_to(repo).as_posix()
        source_id = package_by_dir.get(parent, _node_id("repository", repo.name))
        for requirement in project.get("dependencies", []):
            name = _dependency_name(str(requirement))
            if not name:
                continue
            target = _external_node(nodes, name, "declared")
            line = 1
            _add_edge(
                edges,
                {
                    "id": _edge_id("depends_on", source_id, target, rel, line),
                    "kind": "depends_on",
                    "source": source_id,
                    "target": target,
                    "truth": "declared",
                    "confidence": "high",
                    "reason": "Declared in project.dependencies.",
                    "evidence": [_evidence(rel, line, "manifest")],
                },
            )
        for name, target in sorted(project.get("scripts", {}).items()):
            scripts.append((str(name), str(target), rel))
    return scripts


def _source_base(remote: str, revision: str) -> str:
    if not remote or not revision:
        return ""
    match = re.match(r"git@github\.com:(.+?)(?:\.git)?$", remote)
    if match:
        return f"https://github.com/{match.group(1).removesuffix('.git')}/blob/{revision}/"
    match = re.match(r"https://github\.com/(.+?)(?:\.git)?$", remote)
    if match:
        return f"https://github.com/{match.group(1).removesuffix('.git')}/blob/{revision}/"
    return ""


def build(repo: Path, *, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    """Build a conservative Python code graph for ``repo``.

    Parse failures and unsupported coverage remain in the snapshot receipt.
    Calls are emitted only when a target resolves to a known local symbol.
    """
    repo = repo.resolve()
    code_files = _code_files(repo, exclude)
    files = [path for path in code_files if path.suffix.lower() == ".py"]
    unsupported = Counter(
        LANGUAGES[path.suffix.lower()]
        for path in code_files
        if path.suffix.lower() != ".py"
    )
    modules: list[_Module] = []
    failures = []
    for path in files:
        rel = _relative(path, repo)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text, filename=rel)
        except (OSError, SyntaxError) as error:
            failures.append(
                {
                    "path": rel,
                    "line": getattr(error, "lineno", 0) or 0,
                    "message": str(error),
                }
            )
            continue
        module = _Module(
            path=rel,
            name=_module_name(Path(rel)),
            id=_node_id("module", rel),
            tree=tree,
            symbols=[],
            is_package=path.name == "__init__.py",
        )
        module.symbols = _symbol_rows(module)
        modules.append(module)

    revision = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "remote", "get-url", "origin")
    dirty = bool(_git(repo, "status", "--porcelain"))
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    repo_id = _node_id("repository", repo.name)
    _add_node(
        nodes,
        {
            "id": repo_id,
            "kind": "repository",
            "label": repo.name,
            "truth": "static",
            "attributes": {},
            "evidence": [],
        },
    )

    module_by_name = {module.name: module for module in modules}
    symbol_by_qualified = {
        symbol.qualified_name: symbol for module in modules for symbol in module.symbols
    }
    package_by_dir: dict[str, str] = {}
    for module in modules:
        if module.is_package:
            directory = Path(module.path).parent.as_posix()
            package_id = _node_id("package", module.name or directory)
            package_by_dir[directory] = package_id
            _add_node(
                nodes,
                {
                    "id": package_id,
                    "kind": "package",
                    "label": module.name or directory,
                    "path": directory,
                    "line": 1,
                    "truth": "static",
                    "parent": repo_id,
                    "attributes": {"qualified_name": module.name},
                    "evidence": [_evidence(module.path, 1, "python-ast")],
                },
            )
            _add_edge(
                edges,
                {
                    "id": _edge_id("contains", repo_id, package_id, module.path, 1),
                    "kind": "contains",
                    "source": repo_id,
                    "target": package_id,
                    "truth": "static",
                    "confidence": "high",
                    "reason": "Python package directory contains __init__.py.",
                    "evidence": [_evidence(module.path, 1, "python-ast")],
                },
            )

    def owning_package(module: _Module) -> str:
        candidates = [
            (directory, package_id)
            for directory, package_id in package_by_dir.items()
            if module.path == f"{directory}/__init__.py"
            or module.path.startswith(directory.rstrip("/") + "/")
        ]
        if not candidates:
            return repo_id
        return max(candidates, key=lambda item: len(item[0]))[1]

    for module in modules:
        parent = owning_package(module)
        _add_node(
            nodes,
            {
                "id": module.id,
                "kind": "module",
                "label": module.name or module.path,
                "path": module.path,
                "line": 1,
                "truth": "static",
                "parent": parent,
                "attributes": {"qualified_name": module.name},
                "evidence": [_evidence(module.path, 1, "python-ast")],
            },
        )
        _add_edge(
            edges,
            {
                "id": _edge_id("contains", parent, module.id, module.path, 1),
                "kind": "contains",
                "source": parent,
                "target": module.id,
                "truth": "static",
                "confidence": "high",
                "reason": "Module is located inside this repository or package.",
                "evidence": [_evidence(module.path, 1, "python-ast")],
            },
        )
        for symbol in module.symbols:
            _add_node(
                nodes,
                {
                    "id": symbol.id,
                    "kind": symbol.kind,
                    "label": symbol.name,
                    "path": module.path,
                    "line": getattr(symbol.node, "lineno", 1),
                    "truth": "static",
                    "parent": module.id,
                    "attributes": _symbol_attributes(symbol),
                    "evidence": [
                        _evidence(
                            module.path,
                            getattr(symbol.node, "lineno", 1),
                            "python-ast",
                        )
                    ],
                },
            )
            _add_edge(
                edges,
                {
                    "id": _edge_id(
                        "contains",
                        module.id,
                        symbol.id,
                        module.path,
                        getattr(symbol.node, "lineno", 1),
                    ),
                    "kind": "contains",
                    "source": module.id,
                    "target": symbol.id,
                    "truth": "static",
                    "confidence": "high",
                    "reason": "Python AST definition belongs to this module.",
                    "evidence": [
                        _evidence(
                            module.path,
                            getattr(symbol.node, "lineno", 1),
                            "python-ast",
                        )
                    ],
                },
            )

    for module in modules:
        aliases: dict[str, tuple[str, str]] = {}
        for statement in ast.walk(module.tree):
            targets: list[tuple[str, str]] = []
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    imported_name = alias.name
                    local = module_by_name.get(imported_name)
                    if local:
                        target_id = local.id
                        aliases[alias.asname or imported_name.split(".")[0]] = (
                            "module",
                            imported_name,
                        )
                    else:
                        target_id = _external_node(nodes, imported_name, "static")
                    targets.append((target_id, imported_name))
            elif isinstance(statement, ast.ImportFrom):
                base = _resolve_relative(module, statement)
                for alias in statement.names:
                    if alias.name == "*":
                        continue
                    candidate = ".".join(part for part in (base, alias.name) if part)
                    if candidate in module_by_name:
                        target_id = module_by_name[candidate].id
                        aliases[alias.asname or alias.name] = ("module", candidate)
                    elif base in module_by_name:
                        target_id = module_by_name[base].id
                        qualified = f"{base}.{alias.name}" if base else alias.name
                        if qualified in symbol_by_qualified:
                            aliases[alias.asname or alias.name] = ("symbol", qualified)
                    else:
                        target_id = _external_node(nodes, base or candidate, "static")
                    targets.append((target_id, candidate or base))
            else:
                continue
            for target_id, imported_name in targets:
                line = getattr(statement, "lineno", 1)
                _add_edge(
                    edges,
                    {
                        "id": _edge_id("imports", module.id, target_id, module.path, line),
                        "kind": "imports",
                        "source": module.id,
                        "target": target_id,
                        "truth": "static",
                        "confidence": "high",
                        "reason": f"Python AST import resolves {imported_name!r} to this node.",
                        "evidence": [_evidence(module.path, line, "python-ast")],
                    },
                )

        local_symbols = {symbol.name: symbol for symbol in module.symbols if not symbol.class_name}
        methods = {
            (symbol.class_name, symbol.name): symbol
            for symbol in module.symbols
            if symbol.class_name
        }
        for symbol in module.symbols:
            collector = _Calls(symbol.node)
            collector.visit(symbol.node)
            for call in collector.calls:
                target: _Symbol | None = None
                if isinstance(call.func, ast.Name):
                    target = local_symbols.get(call.func.id)
                    alias = aliases.get(call.func.id)
                    if target is None and alias and alias[0] == "symbol":
                        target = symbol_by_qualified.get(alias[1])
                elif isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
                    owner = call.func.value.id
                    if owner in {"self", "cls"} and symbol.class_name:
                        target = methods.get((symbol.class_name, call.func.attr))
                    else:
                        alias = aliases.get(owner)
                        if alias and alias[0] == "module":
                            target = symbol_by_qualified.get(f"{alias[1]}.{call.func.attr}")
                if target is None or target.id == symbol.id:
                    continue
                line = getattr(call, "lineno", getattr(symbol.node, "lineno", 1))
                _add_edge(
                    edges,
                    {
                        "id": _edge_id("calls", symbol.id, target.id, module.path, line),
                        "kind": "calls",
                        "source": symbol.id,
                        "target": target.id,
                        "truth": "static",
                        "confidence": "medium",
                        "reason": "Python AST call target resolved to a known local symbol.",
                        "evidence": [_evidence(module.path, line, "python-ast")],
                    },
                )

    scripts = _declared_dependencies(repo, nodes, edges, package_by_dir)
    for name, target_text, manifest_path in scripts:
        entry_id = _node_id("entrypoint", name)
        _add_node(
            nodes,
            {
                "id": entry_id,
                "kind": "entrypoint",
                "label": name,
                "path": manifest_path,
                "line": 1,
                "truth": "declared",
                "parent": repo_id,
                "attributes": {"target": target_text},
                "evidence": [_evidence(manifest_path, 1, "manifest")],
            },
        )
        qualified = target_text.split("[", 1)[0].replace(":", ".")
        target = symbol_by_qualified.get(qualified)
        if target:
            _add_edge(
                edges,
                {
                    "id": _edge_id("invokes", entry_id, target.id, manifest_path, 1),
                    "kind": "invokes",
                    "source": entry_id,
                    "target": target.id,
                    "truth": "declared",
                    "confidence": "high",
                    "reason": "Target is declared in project.scripts and resolves locally.",
                    "evidence": [_evidence(manifest_path, 1, "manifest")],
                },
            )

    graph = {
        "contract": CONTRACT,
        "snapshot": {
            "repository": repo.name,
            "revision": revision,
            "dirty": dirty,
            "remote": remote,
            "source_base": "" if dirty else _source_base(remote, revision),
            "generated_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "analyzers": [{"name": "artoo-python-ast", "version": "1"}],
            "coverage": {
                "candidate_files": len(files),
                "parsed_files": len(modules),
                "parse_failures": failures,
                "unsupported_languages": [
                    {"language": language, "files": count}
                    for language, count in sorted(unsupported.items())
                ],
            },
            "exclusions": list(exclude),
            "truncation": {"applied": False, "reason": ""},
        },
        "nodes": sorted(nodes.values(), key=lambda row: row["id"]),
        "edges": sorted(edges.values(), key=lambda row: row["id"]),
        "traces": [],
        "views": [
            {
                "id": "overview",
                "question": "What are the main code areas and their direct relationships?",
                "direction": "both",
                "depth": 2,
                "budget": 80,
                "layers": ["declared", "static", "runtime", "inferred"],
            },
            {
                "id": "calls",
                "question": "Which declared entry points and static calls connect local symbols?",
                "direction": "outgoing",
                "depth": 4,
                "budget": 100,
                "layers": ["declared", "static"],
                "edge_kinds": ["invokes", "calls"],
            },
        ],
    }
    problems = validate(graph)
    if problems:
        raise CodeGraphError("generated invalid graph: " + "; ".join(problems[:5]))
    return graph


def _safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def validate(graph: Any) -> list[str]:
    """Return actionable contract violations without requiring jsonschema."""
    problems = []
    if not isinstance(graph, dict):
        return ["graph must be a JSON object"]
    if graph.get("contract") != CONTRACT:
        problems.append(f"contract must be {CONTRACT!r}")
    snapshot = graph.get("snapshot")
    if not isinstance(snapshot, dict):
        problems.append("snapshot must be an object")
    for field in ("nodes", "edges", "traces", "views"):
        if not isinstance(graph.get(field), list):
            problems.append(f"{field} must be an array")
    if problems:
        return problems

    node_ids: set[str] = set()
    for index, node in enumerate(graph["nodes"]):
        where = f"nodes[{index}]"
        if not isinstance(node, dict):
            problems.append(f"{where} must be an object")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            problems.append(f"{where}.id must be a non-empty string")
        elif node_id in node_ids:
            problems.append(f"duplicate node id {node_id!r}")
        else:
            node_ids.add(node_id)
        if node.get("kind") not in NODE_KINDS:
            problems.append(f"{where}.kind is not recognized: {node.get('kind')!r}")
        if node.get("truth") not in TRUTH_CLASSES:
            problems.append(f"{where}.truth is not recognized: {node.get('truth')!r}")
        if "path" in node and not _safe_relative(node["path"]):
            problems.append(f"{where}.path must be a repository-relative path")
        if "line" in node and (not isinstance(node["line"], int) or node["line"] < 1):
            problems.append(f"{where}.line must be a positive integer")

    for index, node in enumerate(graph["nodes"]):
        if not isinstance(node, dict):
            continue
        parent = node.get("parent")
        if parent is not None and parent != "":
            if not isinstance(parent, str) or parent not in node_ids:
                problems.append(f"nodes[{index}].parent references a missing node")

    edge_ids: set[str] = set()
    for index, edge in enumerate(graph["edges"]):
        where = f"edges[{index}]"
        if not isinstance(edge, dict):
            problems.append(f"{where} must be an object")
            continue
        edge_id = edge.get("id")
        if not isinstance(edge_id, str) or not edge_id:
            problems.append(f"{where}.id must be a non-empty string")
        elif edge_id in edge_ids:
            problems.append(f"duplicate edge id {edge_id!r}")
        else:
            edge_ids.add(edge_id)
        if edge.get("kind") not in EDGE_KINDS:
            problems.append(f"{where}.kind is not recognized: {edge.get('kind')!r}")
        if edge.get("truth") not in TRUTH_CLASSES:
            problems.append(f"{where}.truth is not recognized: {edge.get('truth')!r}")
        for endpoint in ("source", "target"):
            if edge.get(endpoint) not in node_ids:
                problems.append(f"{where}.{endpoint} references a missing node")
        evidence = edge.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            problems.append(f"{where}.evidence must contain at least one coordinate")
            continue
        for evidence_index, coordinate in enumerate(evidence):
            coordinate_where = f"{where}.evidence[{evidence_index}]"
            if not isinstance(coordinate, dict) or not _safe_relative(coordinate.get("path")):
                problems.append(f"{coordinate_where}.path must be repository-relative")
            if not isinstance(coordinate, dict) or not isinstance(coordinate.get("line"), int):
                problems.append(f"{coordinate_where}.line must be an integer")

    for index, view in enumerate(graph["views"]):
        where = f"views[{index}]"
        if not isinstance(view, dict) or not isinstance(view.get("id"), str):
            problems.append(f"{where}.id must be a string")
            continue
        if view.get("direction", "both") not in DIRECTIONS:
            problems.append(f"{where}.direction is not recognized")
        if not isinstance(view.get("budget", 80), int) or view.get("budget", 80) < 1:
            problems.append(f"{where}.budget must be a positive integer")
        layers = view.get("layers", sorted(TRUTH_CLASSES))
        if not isinstance(layers, list) or not set(layers) <= TRUTH_CLASSES:
            problems.append(f"{where}.layers contains an unrecognized truth class")
        edge_kinds = view.get("edge_kinds", [])
        if not isinstance(edge_kinds, list) or not set(edge_kinds) <= EDGE_KINDS:
            problems.append(f"{where}.edge_kinds contains an unrecognized relationship kind")
    return problems


def load(path: Path) -> dict[str, Any]:
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CodeGraphError(f"could not read {path}: {error}") from error
    problems = validate(graph)
    if problems:
        detail = "; ".join(problems[:8])
        raise CodeGraphError(
            f"{path} is not a valid {CONTRACT} graph: {detail}. "
            "Run `artoo map schema` for the contract."
        )
    return graph


def write(graph: dict[str, Any], path: Path) -> Path:
    problems = validate(graph)
    if problems:
        raise CodeGraphError("refusing to write invalid graph: " + "; ".join(problems[:8]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_browser_data(graph: dict[str, Any], directory: Path) -> tuple[Path, Path]:
    """Write JSON plus a file://-safe global loader for the same graph."""
    json_path = write(graph, directory / "codegraph.json")
    js_path = directory / "codegraph.js"
    compact = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    js_path.write_text(f"window.ARTOO_CODEGRAPH = {compact};\n", encoding="utf-8")
    return json_path, js_path


def _node_index(graph: dict[str, Any]) -> dict[str, dict]:
    return {node["id"]: node for node in graph["nodes"]}


def resolve_node(graph: dict[str, Any], reference: str) -> dict:
    """Resolve a stable id, path, qualified name, or unique label."""
    nodes = graph["nodes"]
    by_id = _node_index(graph)
    if reference in by_id:
        return by_id[reference]
    exact = [
        node
        for node in nodes
        if reference
        in {
            node.get("path", ""),
            node.get("label", ""),
            node.get("attributes", {}).get("qualified_name", ""),
        }
    ]
    if len(exact) == 1:
        return exact[0]
    folded = reference.casefold()
    partial = [
        node
        for node in nodes
        if folded in node.get("label", "").casefold()
        or folded in node.get("path", "").casefold()
        or folded in node.get("attributes", {}).get("qualified_name", "").casefold()
    ]
    matches = exact or partial
    if not matches:
        raise CodeGraphError(
            f"no node matches {reference!r}; use `artoo map view GRAPH --format json` "
            "to inspect stable ids"
        )
    if len(matches) > 1:
        choices = ", ".join(node["id"] for node in matches[:6])
        raise CodeGraphError(f"{reference!r} is ambiguous; use one of: {choices}")
    return matches[0]


def _view_definition(graph: dict[str, Any], name: str) -> dict:
    for view in graph.get("views", []):
        if view.get("id") == name:
            return view
    available = ", ".join(view.get("id", "?") for view in graph.get("views", []))
    raise CodeGraphError(f"no view named {name!r} (available: {available or 'none'})")


def _overview_ids(graph: dict[str, Any], budget: int, layers: set[str]) -> list[str]:
    invoked = {
        endpoint
        for edge in graph["edges"]
        if edge["kind"] == "invokes" and edge["truth"] in layers
        for endpoint in (edge["source"], edge["target"])
    }

    def priority(node: dict) -> tuple[int, str]:
        kind = node["kind"]
        if kind == "repository":
            rank = 0
        elif kind == "entrypoint":
            rank = 1
        elif kind == "package":
            rank = 2
        elif node["id"] in invoked:
            rank = 3
        elif kind == "module":
            rank = 4
        elif kind == "external" and node.get("attributes", {}).get("scope") == "third_party":
            rank = 5
        elif kind in {"service", "datastore"}:
            rank = 6
        elif kind in {"class", "function"}:
            rank = 7
        else:
            rank = 8
        return rank, node["id"]

    candidates = [node for node in graph["nodes"] if node["truth"] in layers]
    return [node["id"] for node in sorted(candidates, key=priority)[:budget]]


def select_view(
    graph: dict[str, Any],
    *,
    name: str = "overview",
    focus: str = "",
    direction: str | None = None,
    depth: int | None = None,
    budget: int | None = None,
    layers: set[str] | None = None,
) -> dict[str, Any]:
    """Project a bounded, question-specific subgraph."""
    definition = _view_definition(graph, name)
    direction = direction or definition.get("direction", "both")
    depth = definition.get("depth", 2) if depth is None else depth
    budget = definition.get("budget", 80) if budget is None else budget
    layers = layers or set(definition.get("layers", TRUTH_CLASSES))
    if direction not in DIRECTIONS:
        raise CodeGraphError(f"direction must be one of {', '.join(sorted(DIRECTIONS))}")
    if depth < 0:
        raise CodeGraphError("depth must be zero or greater")
    if budget < 1:
        raise CodeGraphError("budget must be at least one node")
    if not layers or not layers <= TRUTH_CLASSES:
        raise CodeGraphError("layers must contain declared, static, runtime, or inferred")

    allowed_kinds = set(definition.get("edge_kinds", EDGE_KINDS))
    allowed_edges = [
        edge
        for edge in graph["edges"]
        if edge["truth"] in layers and edge["kind"] in allowed_kinds
    ]
    if focus:
        root = resolve_node(graph, focus)
        selected = [root["id"]]
        seen = {root["id"]}
        queue = deque([(root["id"], 0)])
        while queue and len(selected) < budget:
            current, distance = queue.popleft()
            if distance >= depth:
                continue
            neighbors = []
            for edge in allowed_edges:
                if direction in {"outgoing", "both"} and edge["source"] == current:
                    neighbors.append(edge["target"])
                if direction in {"incoming", "both"} and edge["target"] == current:
                    neighbors.append(edge["source"])
            for neighbor in sorted(set(neighbors)):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                selected.append(neighbor)
                queue.append((neighbor, distance + 1))
                if len(selected) >= budget:
                    break
    else:
        if definition.get("edge_kinds"):
            degree: Counter[str] = Counter()
            for edge in allowed_edges:
                degree[edge["source"]] += 1
                degree[edge["target"]] += 1
            node_index = _node_index(graph)
            selected = sorted(
                degree,
                key=lambda node_id: (
                    0 if node_index[node_id]["kind"] == "entrypoint" else 1,
                    -degree[node_id],
                    node_id,
                ),
            )[:budget]
        else:
            selected = _overview_ids(graph, budget, layers)
    selected_ids = set(selected)
    nodes = [node for node in graph["nodes"] if node["id"] in selected_ids]
    edges = [
        edge
        for edge in allowed_edges
        if edge["source"] in selected_ids and edge["target"] in selected_ids
    ]
    eligible_count = sum(1 for node in graph["nodes"] if node["truth"] in layers)
    return {
        "contract": VIEW_CONTRACT,
        "snapshot": graph["snapshot"],
        "view": {
            "id": name,
            "question": definition.get("question", ""),
            "focus": focus,
            "direction": direction,
            "depth": depth,
            "budget": budget,
            "layers": sorted(layers),
            "truncated": len(nodes) < eligible_count,
            "eligible_nodes": eligible_count,
        },
        "nodes": nodes,
        "edges": edges,
    }


def explain(graph: dict[str, Any], reference: str) -> dict[str, Any]:
    node = resolve_node(graph, reference)
    return {
        "node": node,
        "incoming": [edge for edge in graph["edges"] if edge["target"] == node["id"]],
        "outgoing": [edge for edge in graph["edges"] if edge["source"] == node["id"]],
    }


def find_path(
    graph: dict[str, Any], source_ref: str, target_ref: str, *, layers: set[str] | None = None
) -> dict[str, Any]:
    source = resolve_node(graph, source_ref)
    target = resolve_node(graph, target_ref)
    layers = layers or set(TRUTH_CLASSES)
    edges = [edge for edge in graph["edges"] if edge["truth"] in layers]
    outgoing: dict[str, list[dict]] = {}
    for edge in edges:
        outgoing.setdefault(edge["source"], []).append(edge)
    queue = deque([source["id"]])
    previous: dict[str, tuple[str, dict]] = {}
    seen = {source["id"]}
    while queue:
        current = queue.popleft()
        if current == target["id"]:
            break
        for edge in sorted(outgoing.get(current, []), key=lambda row: row["id"]):
            neighbor = edge["target"]
            if neighbor in seen:
                continue
            seen.add(neighbor)
            previous[neighbor] = (current, edge)
            queue.append(neighbor)
    if target["id"] not in seen:
        raise CodeGraphError(
            f"no directed path from {source_ref!r} to {target_ref!r} in layers "
            f"{', '.join(sorted(layers))}"
        )
    node_ids = [target["id"]]
    path_edges = []
    while node_ids[-1] != source["id"]:
        parent, edge = previous[node_ids[-1]]
        path_edges.append(edge)
        node_ids.append(parent)
    node_ids.reverse()
    path_edges.reverse()
    nodes = _node_index(graph)
    return {
        "source": source["id"],
        "target": target["id"],
        "nodes": [nodes[node_id] for node_id in node_ids],
        "edges": path_edges,
    }


def context(
    graph: dict[str, Any], query: str, *, budget_tokens: int = 1200
) -> dict[str, Any]:
    """Rank source coordinates for a question under an approximate token budget.

    This is intentionally transparent rather than semantic magic: query term
    matches, entry points, public definitions, and typed graph degree determine
    the score. Each returned row states its reasons.
    """
    if budget_tokens < 32:
        raise CodeGraphError("context budget must be at least 32 tokens")
    terms = {
        term.casefold()
        for term in re.findall(r"[A-Za-z_][A-Za-z0-9_.-]*", query)
        if len(term) > 1
    }
    nodes = _node_index(graph)
    scores: dict[str, float] = {node_id: 0.0 for node_id in nodes}
    reasons: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    weights = {
        "invokes": 8.0,
        "calls": 5.0,
        "imports": 3.0,
        "depends_on": 2.0,
        "contains": 0.5,
    }
    for node_id, node in nodes.items():
        if node["kind"] == "entrypoint":
            scores[node_id] += 18
            reasons[node_id].append("declared entry point")
        if node["kind"] in {"class", "function"} and node.get("attributes", {}).get(
            "visibility"
        ) == "public":
            scores[node_id] += 3
            reasons[node_id].append("public definition")
        haystack = " ".join(
            (
                node.get("label", ""),
                node.get("path", ""),
                node.get("attributes", {}).get("qualified_name", ""),
                node.get("attributes", {}).get("doc", ""),
            )
        ).casefold()
        matched = sorted(term for term in terms if term in haystack)
        if matched:
            scores[node_id] += 30 + 8 * len(matched)
            reasons[node_id].append("query match: " + ", ".join(matched[:4]))
    for edge in graph["edges"]:
        weight = weights.get(edge["kind"], 1.0)
        scores[edge["source"]] += weight
        scores[edge["target"]] += weight
        if weight >= 3:
            reasons[edge["source"]].append(f"{edge['kind']} relationship")
            reasons[edge["target"]].append(f"{edge['kind']} relationship")

    ranked = []
    for node_id, score in scores.items():
        node = nodes[node_id]
        if not node.get("path"):
            continue
        attributes = node.get("attributes", {})
        coordinate = f"{node['path']}:{node.get('line', 1)}"
        label = attributes.get("signature") or attributes.get("qualified_name") or node["label"]
        note = attributes.get("doc", "")
        text = f"- {coordinate} · {node['kind']} · {label}"
        if note:
            text += f" — {note}"
        ranked.append(
            {
                "id": node_id,
                "path": node["path"],
                "line": node.get("line", 1),
                "kind": node["kind"],
                "truth": node["truth"],
                "label": label,
                "score": round(score, 3),
                "reasons": sorted(set(reasons[node_id]))[:8],
                "text": text,
            }
        )
    ranked.sort(key=lambda row: (-row["score"], row["path"], row["line"], row["id"]))
    selected = []
    text_rows = []
    estimated_tokens = 0
    for row in ranked:
        row_tokens = max(1, math.ceil(len(row["text"]) / 4))
        if text_rows and estimated_tokens + row_tokens > budget_tokens:
            continue
        if row_tokens > budget_tokens:
            continue
        selected.append({key: value for key, value in row.items() if key != "text"})
        text_rows.append(row["text"])
        estimated_tokens += row_tokens
        if estimated_tokens >= budget_tokens:
            break
    return {
        "contract": "artoo-codegraph-context/1",
        "snapshot": graph["snapshot"],
        "query": query,
        "budget_tokens": budget_tokens,
        "estimated_tokens": estimated_tokens,
        "items": selected,
        "text": "\n".join(text_rows) + ("\n" if text_rows else ""),
    }


def to_mermaid(view: dict[str, Any]) -> str:
    """Compile a validated bounded view to deterministic Mermaid source."""
    node_ids = {node["id"]: f"n{index}" for index, node in enumerate(view["nodes"])}
    lines = ["flowchart LR"]
    for node in view["nodes"]:
        label = str(node.get("label", node["id"])).replace('"', "'").replace("\n", " ")
        mermaid_id = node_ids[node["id"]]
        if node["kind"] == "external":
            lines.append(f'  {mermaid_id}(["{label}"])')
        elif node["kind"] == "entrypoint":
            lines.append(f'  {mermaid_id}{{{{"{label}"}}}}')
        else:
            lines.append(f'  {mermaid_id}["{label}"]')
        lines.append(f"  class {mermaid_id} truth-{node['truth']}")
    for index, edge in enumerate(view["edges"]):
        source = node_ids[edge["source"]]
        target = node_ids[edge["target"]]
        label = edge["kind"].replace("_", " ")
        arrow = "-.->" if edge["truth"] == "inferred" else "-->"
        lines.append(f"  {source} {arrow}|{label}| {target}")
        if edge["truth"] == "runtime":
            lines.append(f"  linkStyle {index} stroke:#277553,stroke-width:2px")
    lines.extend(
        [
            "  classDef truth-declared stroke:#3e63b4,stroke-width:2px",
            "  classDef truth-static stroke:#4a5264",
            "  classDef truth-runtime stroke:#277553,stroke-width:2px",
            "  classDef truth-inferred stroke:#8a5a00,stroke-dasharray:5 4",
        ]
    )
    return "\n".join(lines) + "\n"
