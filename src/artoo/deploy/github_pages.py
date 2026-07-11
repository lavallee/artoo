"""GitHub Pages deploys — where the deployment intelligence lives.

Pages repos exist in three real-world configurations, and getting this
wrong is the most common way a publish silently fails:

- **docs mode** ("legacy" build): Pages serves ``/docs`` (or the root) of a
  branch directly. Publishing means copying the built site into that folder
  and committing.
- **workflow mode**: an Actions workflow uploads an assembled directory via
  ``actions/deploy-pages``. Publishing means placing the site where the
  workflow looks.
- **branch mode**: a dedicated branch (classically ``gh-pages``) holds the
  published tree.

When the ``gh`` CLI is available, the adapter reads the repo's *actual*
Pages configuration and routes accordingly — and refuses to guess when what
it finds contradicts the manifest. Without ``gh``, the manifest must name
the mode explicitly.

Manifest config::

    [deploy.github-pages]
    mode = "docs"          # docs | workflow | branch | "" (auto-detect)
    subpath = "explainer"  # where under the published root; default: slug
    docs_dir = "docs"      # docs mode
    publish_dir = "_site"  # workflow mode
    branch = "gh-pages"    # branch mode
    commit = true          # commit the copied site (never pushes)
    push = false           # push after committing
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import ClassVar

from .. import firewall
from .base import DeployContext, DeployResult


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _git_commit(cwd: Path, message: str) -> subprocess.CompletedProcess:
    """Commit with a fallback identity for environments (CI, containers)
    where none is configured — a deploy shouldn't die on git identity."""
    cmd = ["git"]
    if not _run(["git", "config", "user.email"], cwd=cwd).stdout.strip():
        cmd += ["-c", "user.name=artoo", "-c", "user.email=artoo@localhost"]
    cmd += ["commit", "-m", message]
    return _run(cmd, cwd=cwd)


def _commit_outcome(proc: subprocess.CompletedProcess, msg: str) -> tuple[bool, str]:
    """(ok, action line) — distinguish a clean tree from a real failure."""
    if proc.returncode == 0:
        return True, f"committed: {msg}"
    output = proc.stdout + proc.stderr
    if "nothing to commit" in output or "nothing added to commit" in output:
        return True, "nothing to commit (site unchanged)"
    return False, (proc.stderr or proc.stdout).strip()


def parse_owner_repo(remote_url: str) -> tuple[str, str] | None:
    url = remote_url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("git@") and ":" in url:
        url = url.split(":", 1)[1]
    elif "github.com/" in url:
        url = url.split("github.com/", 1)[1]
    else:
        return None
    parts = url.strip("/").split("/")
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def detect_pages_config(repo_root: Path) -> dict | None:
    """Ask the GitHub API (via gh) how Pages is actually configured.

    Returns the API payload, ``{"disabled": True}`` when Pages is off, or
    None when detection isn't possible (no gh, no GitHub remote).
    """
    if not shutil.which("gh"):
        return None
    remote = _run(["git", "remote", "get-url", "origin"], cwd=repo_root)
    if remote.returncode != 0:
        return None
    parsed = parse_owner_repo(remote.stdout)
    if not parsed:
        return None
    owner, repo = parsed
    proc = _run(["gh", "api", f"repos/{owner}/{repo}/pages"])
    if proc.returncode != 0:
        if "Not Found" in (proc.stdout + proc.stderr):
            return {"disabled": True, "owner": owner, "repo": repo}
        return None
    payload = json.loads(proc.stdout)
    payload["owner"] = owner
    payload["repo"] = repo
    return payload


def _mode_from_detection(detected: dict) -> tuple[str, dict]:
    """Map an API payload to (mode, details)."""
    if detected.get("disabled"):
        return "disabled", {}
    if detected.get("build_type") == "workflow":
        return "workflow", {}
    source = detected.get("source") or {}
    return "docs", {
        "branch": source.get("branch", "main"),
        "path": (source.get("path") or "/docs").strip("/") or ".",
    }


class GitHubPagesDeployer:
    name: ClassVar[str] = "github-pages"

    def deploy(self, ctx: DeployContext) -> DeployResult:
        repo_root = ctx.repo_root
        if repo_root is None:
            return DeployResult(
                ok=False,
                message="github-pages adapter needs the artifact to live in a git repo",
            )

        mode = ctx.config.get("mode", "")
        detected = detect_pages_config(repo_root)

        if detected is not None:
            detected_mode, details = _mode_from_detection(detected)
            if detected_mode == "disabled":
                owner, repo = detected["owner"], detected["repo"]
                if not mode:
                    return DeployResult(
                        ok=False,
                        message=(
                            f"GitHub Pages is not enabled for {owner}/{repo}. Enable it "
                            "(Settings → Pages, or `gh api -X POST repos/"
                            f"{owner}/{repo}/pages -f build_type=legacy "
                            '-f "source[branch]=main" -f "source[path]=/docs"`), '
                            "or set an explicit mode in [deploy.github-pages]."
                        ),
                    )
            elif not mode:
                mode = detected_mode
                if mode == "docs":
                    ctx.config.setdefault("docs_dir", details["path"])
            elif mode != detected_mode:
                return DeployResult(
                    ok=False,
                    message=(
                        f"manifest says mode={mode!r} but the repo's Pages config is "
                        f"{detected_mode!r} ({details or detected.get('build_type')}). "
                        "Fix one of them — refusing to guess."
                    ),
                )
        elif not mode:
            return DeployResult(
                ok=False,
                message=(
                    "cannot detect the repo's Pages configuration (gh CLI missing or no "
                    "GitHub remote) and no mode is set. Set [deploy.github-pages] "
                    'mode = "docs" | "workflow" | "branch".'
                ),
            )

        if mode == "docs":
            return self._deploy_into_tree(ctx, repo_root, ctx.config.get("docs_dir", "docs"))
        if mode == "workflow":
            publish_dir = ctx.config.get("publish_dir", "")
            if not publish_dir:
                return DeployResult(
                    ok=False,
                    message=(
                        "workflow mode needs [deploy.github-pages] publish_dir — the "
                        "directory your Pages workflow uploads."
                    ),
                )
            return self._deploy_into_tree(ctx, repo_root, publish_dir)
        if mode == "branch":
            return self._deploy_branch(ctx, repo_root)
        return DeployResult(ok=False, message=f"unknown github-pages mode {mode!r}")

    # -- docs/workflow: copy into a tracked folder of the working tree ------

    def _deploy_into_tree(self, ctx: DeployContext, repo_root: Path, tree_dir: str) -> DeployResult:
        subpath = ctx.config.get("subpath", ctx.manifest.slug)
        published_root = repo_root / tree_dir
        dest = published_root / subpath if subpath else published_root
        actions = []

        owns_root = bool(ctx.config.get("own_root", False))
        if (
            not subpath
            and not owns_root
            and published_root.exists()
            and any(published_root.iterdir())
        ):
            return DeployResult(
                ok=False,
                message=(
                    f"refusing to replace the entire {tree_dir}/ tree (subpath is empty "
                    "and the folder is not). Set subpath to publish alongside what's "
                    "there, or own_root = true if this artifact owns the whole tree."
                ),
            )

        # In-place artifact: the site already lives exactly where Pages
        # serves it (weaver-style). Nothing to copy — just note what the
        # firewall would have withheld (it's served regardless here) and
        # fall through to commit.
        in_place = (
            dest.exists()
            and dest.resolve() == ctx.manifest.site_dir.resolve()
        )
        if in_place:
            held = firewall.withheld(ctx.manifest.site_dir)
            if ctx.dry_run:
                return DeployResult(
                    ok=True,
                    message="dry run — site is in place, would commit",
                    actions=[f"site already lives at {dest.relative_to(repo_root)}"],
                )
            actions.append(f"site already lives at {dest.relative_to(repo_root)} — nothing to copy")
            if held:
                actions.append(
                    "note: served in place, so the firewall cannot withhold: "
                    + ", ".join(str(p) for p in held[:6])
                )
            nojekyll = published_root / ".nojekyll"
            if not nojekyll.exists():
                nojekyll.touch()
                actions.append(f"created {nojekyll.relative_to(repo_root)}")
            return self._commit_tree(ctx, repo_root, dest, nojekyll, actions)

        if ctx.dry_run:
            return DeployResult(
                ok=True,
                message="dry run — nothing copied",
                actions=[f"would copy staged site to {dest}"],
            )

        if dest.exists() and (subpath or owns_root):
            shutil.rmtree(dest)
        shutil.copytree(ctx.staged, dest, dirs_exist_ok=not (subpath or owns_root))
        actions.append(f"copied site to {dest.relative_to(repo_root)}")

        nojekyll = published_root / ".nojekyll"
        if not nojekyll.exists():
            nojekyll.touch()
            actions.append(f"created {nojekyll.relative_to(repo_root)}")

        return self._commit_tree(ctx, repo_root, dest, nojekyll, actions)

    def _commit_tree(
        self, ctx: DeployContext, repo_root: Path, dest: Path,
        nojekyll: Path, actions: list[str],
    ) -> DeployResult:
        if not ctx.config.get("commit", True):
            actions.append("not committed (commit = false)")
            return DeployResult(ok=True, message="published into the Pages tree", actions=actions)

        rel = str(dest.relative_to(repo_root))
        _run(["git", "add", rel, str(nojekyll.relative_to(repo_root))], cwd=repo_root)
        msg = f"artoo deploy: {ctx.manifest.slug}"
        ok, action = _commit_outcome(_git_commit(repo_root, msg), msg)
        if not ok:
            return DeployResult(
                ok=False, message="staged, but git commit failed",
                actions=actions + [action],
            )
        actions.append(action)
        if ctx.config.get("push", False):
            push = _run(["git", "push"], cwd=repo_root)
            if push.returncode != 0:
                return DeployResult(
                    ok=False,
                    message="committed, but push failed",
                    actions=actions + [push.stderr.strip()],
                )
            actions.append("pushed")
        else:
            actions.append("not pushed — push when ready (or set push = true)")

        return DeployResult(ok=True, message="published into the Pages tree", actions=actions)

    # -- branch mode: publish tree lives on its own branch ------------------

    def _deploy_branch(self, ctx: DeployContext, repo_root: Path) -> DeployResult:
        branch = ctx.config.get("branch", "gh-pages")
        subpath = ctx.config.get("subpath", ctx.manifest.slug)
        if ctx.dry_run:
            return DeployResult(
                ok=True,
                message="dry run — nothing pushed",
                actions=[f"would publish staged site to branch {branch!r} at /{subpath}"],
            )

        worktree = Path(tempfile.mkdtemp(prefix="artoo-pages-"))
        actions = []
        try:
            have_branch = _run(
                ["git", "rev-parse", "--verify", "--quiet", branch], cwd=repo_root
            ).returncode == 0
            if have_branch:
                added = _run(["git", "worktree", "add", str(worktree), branch], cwd=repo_root)
                if added.returncode != 0:
                    return DeployResult(
                        ok=False, message="git worktree add failed",
                        actions=[added.stderr.strip()],
                    )
            else:
                _run(["git", "worktree", "add", "--detach", str(worktree)], cwd=repo_root)
                _run(["git", "checkout", "--orphan", branch], cwd=worktree)
                _run(["git", "rm", "-rfq", "."], cwd=worktree)
                actions.append(f"created orphan branch {branch!r}")

            dest = worktree / subpath if subpath else worktree
            if dest.exists() and subpath:
                shutil.rmtree(dest)
            shutil.copytree(ctx.staged, dest, dirs_exist_ok=not subpath)
            (worktree / ".nojekyll").touch()

            _run(["git", "add", "-A"], cwd=worktree)
            msg = f"artoo deploy: {ctx.manifest.slug}"
            ok, action = _commit_outcome(_git_commit(worktree, msg), msg)
            if not ok:
                return DeployResult(
                    ok=False, message=f"staged onto {branch!r}, but git commit failed",
                    actions=actions + [action],
                )
            actions.append(action if "nothing" in action else f"committed to {branch!r}: {msg}")

            if ctx.config.get("push", False):
                push = _run(["git", "push", "-u", "origin", branch], cwd=worktree)
                if push.returncode != 0:
                    return DeployResult(
                        ok=False,
                        message=f"committed to {branch!r} but push failed",
                        actions=actions + [push.stderr.strip()],
                    )
                actions.append(f"pushed {branch!r}")
            else:
                actions.append(f"not pushed — `git push origin {branch}` when ready")
            return DeployResult(ok=True, message=f"published to branch {branch!r}", actions=actions)
        finally:
            _run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo_root)


# Staging helper used by the CLI so adapters always see firewall-cleared trees.
def stage_for_deploy(manifest, workdir: Path) -> Path:
    staged = workdir / "staged"
    firewall.stage(manifest, staged)
    return staged
