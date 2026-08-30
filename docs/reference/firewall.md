# The deploy firewall

Research material lives next to the presentation. The firewall is what makes
that safe: publishing is **deny-by-default**, and the rules are structural
rather than a list of ignores someone has to maintain.

## What ships

Only files inside the artifact's site root (`site/` unless `build.site` says
otherwise). Everything else in the artifact directory — `work/`, `notebook/`,
`artifact.toml`, `AGENTS.md`, scratch files — stays in the repo.

## What is withheld even inside `site/`

| Rule | Rationale |
|------|-----------|
| Any path segment starting with `_` | The conventional "working file" marker |
| Any path segment starting with `.` | Except `.nojekyll`, which hosts require |
| `notebook.md`, `notes.md`, `priors.md`, `DECISIONS.md`, `HANDOFF.md` | Research filenames, wherever they land |
| `artifact.toml` | The manifest is repo metadata, not site content |
| Symlinks | Never followed out of the artifact |

So `site/_draft/v2.html` and `site/notes.md` are visible to you and invisible
to the world, with no configuration.

## Seeing it before you publish

```bash
artoo status <artifact>    # lists what would be withheld
artoo deploy <artifact> --dry-run
```

`artoo deploy` stages only the publishable set into a temporary tree and hands
*that* to the adapter. An adapter never sees the artifact directory, so it
cannot publish something the firewall declined.

## The one deliberate opening

A private flip notebook is not projected into `site/data/provenance.json`
unless the manifest opts in:

```toml
[research]
include_private = true
```

That renders a non-public notebook in full into a publishable file. Check what
the panel shows before deploying.
