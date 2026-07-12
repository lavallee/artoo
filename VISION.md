# Vision — artoo

Re-grounded 2026-07-12 against the shipped 0.1 artifact manager, explainer
generator, deployment adapters, and the first external site library.

**North star:** Any durable explanation produced with AI can leave the chat as
a self-contained, evidence-backed artifact that its owning repository can
inspect, reproduce, publish, and keep working after the generating tools move
on.

**North-star metric:** trustworthy artifact deployments — artifacts that pass
the private-file firewall and manifest checks, publish without bespoke repair,
and remain reproducible from their recorded source revision.

## Strategy bets

- **The artifact is the unit.** A small manifest inside the owning repository
  is the canonical contract; inventories, status, deploy routing, and indexes
  are derived from it.
- **Portability and provenance beat convenience.** Sites are self-contained,
  research remains beside the presentation but cannot ship, and every vendored
  dependency is versioned and hash-pinned.
- **Generators and adapters form the ecosystem.** Core stays small and
  keyless while worker CLIs, deployers, and site libraries extend it through
  explicit plugin contracts.

## Non-goals

- A hosted artifact platform, account system, or telemetry service.
- A WYSIWYG site editor or general-purpose web framework.
- Direct model-provider clients or API-key custody in core.
- Replacing the repositories, notebooks, or publishing systems that own the
  underlying work.

## Engine map

- `artifact.toml`, discovery, status, and the firewall define the durable unit.
- `artoo-kit` and external libraries such as `artoo-mermaid` make sites
  portable without coupling their lifecycle to core.
- Generator workers provide analysis and synthesis; flip provides optional
  source custody and claim lineage.
- GitHub Pages, rsync, and command adapters carry one checked artifact into its
  real publishing environment.
