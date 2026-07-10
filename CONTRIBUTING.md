# Contributing to artoo

Thanks for helping. Ground rules that keep artoo coherent:

## Setup

```bash
git clone https://github.com/lavallee/artoo && cd artoo
uv sync
uv run pytest -q
```

## Principles

- **Core stays light.** `pip install artoo` must work with one small
  dependency (`click`). Heavy or network-bound features go behind extras
  or plugins. Model SDKs never enter core — generators shell out to agent
  CLIs the user already has.
- **The firewall is sacred.** Nothing outside an artifact's `site/` root
  ships, ever. Notebook files and `_`/`.`-prefixed paths never ship even
  inside `site/`. Any change touching deploy paths needs tests proving
  the firewall holds.
- **Manifests must diff cleanly.** `artifact.toml` is written with stable
  key order, scalars before tables. Don't introduce nondeterminism.
- **Adapters degrade loudly.** When a deployer or worker can't proceed
  (missing CLI, ambiguous Pages config), it says exactly what it found
  and what to do — it never guesses silently.
- **Ecosystem over monolith.** New generators, deployers, and site
  libraries belong in their own repos using the entry-point groups.
  Reference implementations live here only when they're load-bearing for
  the core experience.

## Tests

One `test_<module>.py` per source module, `tmp_path`-based, no network,
no global state. CI runs `ruff check` + `pytest` on Python 3.12 and 3.13.
