# artoo — working in this repo

artoo generates and manages **artifacts**: self-contained HTML mini-sites that
pair presentation with the research behind it. This file is for anyone working
on artoo itself. If you are *using* artoo to build an artifact, read the
`AGENTS.md` that `artoo init` writes into the artifact, or run `artoo docs`.

## Commands

```bash
uv sync
uv run pytest -q
uv run ruff check src tests
uv run artoo --help
```

CI runs the last two on 3.12 and 3.13. Both must pass before a PR lands.

## Layout

| path | what lives there |
|------|------------------|
| `src/artoo/cli.py` | every command; thin, delegating to modules |
| `src/artoo/manifest.py` | `artifact.toml` — load, validate, deterministic write |
| `src/artoo/firewall.py` | deny-by-default publish rules |
| `src/artoo/build.py` | run build commands, verify, stamp `updated` |
| `src/artoo/markup.py` | CSS vocabulary parser + the invented-class check |
| `src/artoo/docs.py` | `artoo docs`; the single source for all reference text |
| `src/artoo/agent_guide.py` | the `AGENTS.md` written into each artifact |
| `src/artoo/skill.py` | `artoo skill install` |
| `src/artoo/reference/*.md` | authored reference topics |
| `src/artoo/libraries/*/` | site libraries: assets, README, class vocabulary |
| `src/artoo/deploy/`, `generators/` | entry-point plugins |
| `docs/` | the GitHub Pages site — **generated**, see below |

## The reference has one source

`artoo.docs` renders onto four surfaces, and they must not drift apart:

1. `artoo docs <topic>` in a shell
2. `AGENTS.md` inside every artifact `artoo init` creates
3. `SKILL.md` + `references/` from `artoo skill install`
4. `docs/llms.txt`, `docs/llms-full.txt`, `docs/reference/*.md` on the site

Change a reference topic or a library's class vocabulary, then run:

```bash
uv run python scripts/sync-docs-site.py
```

A test fails if `docs/` is stale, so this is not optional.

## Changing a site library

Each library declares its public vocabulary in `libraries/<name>/__init__.py`:

- `CLASSES` — every public class, with a one-line role
- `NAMESPACES` — the class prefixes it owns

**A test asserts `CLASSES` matches the stylesheets exactly**, in both
directions. Add a public class to the CSS and the suite fails until you
document it; delete one and it fails until you remove the entry. That is
deliberate: undocumented vocabulary is vocabulary the next author reverse-
engineers from the stylesheet, which is the failure this surface exists to
remove.

Declaring a namespace has teeth — `artoo build` fails on a class inside it
that the CSS does not define. Only declare a prefix the library genuinely
owns. Generic component names (`card`, `stat`, `toc`) are deliberately not
namespaces, because an artifact's own `.card-hero` is its business, and a
check that cries wolf gets ignored on the day it is right.

Bump the library's `VERSION` when its assets change. Vendored copies are
hash-pinned and never rewritten in place; `artoo lib update` is the explicit
upgrade boundary.

## Conventions

- **Errors are road signs.** Say what went wrong, and name the next command or
  the manifest key that fixes it — in *this* tool's vocabulary. A refusal
  relayed from `flip` that names a `flip` flag artoo does not have sends the
  reader somewhere that does not exist.
- **artoo core makes no model calls and holds no API keys.** Generators shell
  out to agent CLIs already on `PATH`.
- **flip is a soft import.** Everything touching it must no-op cleanly when it
  is absent, and the test suite must pass without it installed.
- **Comments explain why, never what.** Line length 100, ruff-enforced.
