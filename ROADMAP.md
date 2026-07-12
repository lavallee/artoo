# Roadmap — artoo

The next work turns the shipped 0.1 architecture into a dependable practice.
Outcomes are ordered; new adapters or generators do not outrank proving the
core contract on real artifacts.

## Outcome 1 — Prove the artifact contract end to end

- Dogfood the explainer generator on a substantial public repository and land
  the result without disturbing its existing site.
- Make build, status, firewall, revision snapshot, and deploy output
  deterministic enough for CI and review.
- Exercise all three deployment shapes against real repositories and make
  ambiguous host configuration fail with an actionable explanation.

*Graduation:* two independently owned repositories can generate, review, and
publish an artifact using only documented commands. *Kill:* if the manifest
cannot express those deployments without project-specific core changes,
revisit the contract before adding ecosystem breadth.

## Outcome 2 — Make generated explainers trustworthy

- Make every pipeline stage resumable and preserve the analyzed commit,
  worker tier, validation result, and generation date.
- Complete the flip-backed lineage path and retain a plain-files fallback when
  flip is absent.
- Add evaluation fixtures for factual grounding, navigation, offline rendering,
  and private-file leakage.

*Graduation:* a reviewer can trace load-bearing explainer claims to repository
evidence and rerun a failed stage without regenerating the whole artifact.
*Kill:* if generated explainers cannot clear that evidence bar, keep artoo as a
manager/deployer and stop presenting generation as a trusted default.

## Outcome 3 — Stabilize the extension ecosystem

- Version the generator, deployer, library, and worker interfaces with
  compatibility tests and reference packages.
- Prove deliberate library upgrades and drift detection across already-published
  artifacts.
- Publish concise authoring guides for a third-party generator, deployer, and
  site library.

*Graduation:* an external package can extend each plugin surface without an
artoo source checkout. *Kill:* extension points with no second real consumer
stay private implementation details rather than permanent APIs.

## Keeping this file honest

Completed work moves to `CHANGELOG.md`; this file keeps only unresolved bets.
Re-ground it after each minor release or any change to the artifact manifest.
