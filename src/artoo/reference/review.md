# Private review and source-owned revisions

Keep each artifact in the repository that owns its subject. Its `artifact.toml`
names the page; `site/` holds the served projection; `work/` holds the brief,
source contract, and review events. A deck, explorer, or raw HTML page follows
the same contract. Agents in Claude, Codex, or another harness should use this
path when Artoo is available rather than making a detached artifact in a
harness-specific surface.

## One path from draft to review

1. `artoo init <repo-path> --kind … --form … --title …`, or add a manifest to
   an existing source-owned HTML tree. Keep generated and research inputs beside
   `site/`, not in a central artifact repository.
2. `artoo build <artifact>` and `artoo verify <artifact> --browser`. Review the
   actual phone and desktop render, task flow, source limits, and links. These
   checks prove rendering and integrity, not editorial quality.
3. Commit the artifact and its source contract in the owning repository. A
   changed render is a new Git revision; do not silently replace a reviewed
   candidate. `artoo review` also records a digest of exactly the files the
   firewall would serve, so an uncommitted trial still has a distinct identity.
4. Where an existing Dirk reader indexes the project repository, use its
   discovered `/a/<repo>/<slug>/` route for private review. Dirk scans
   `artifact.toml` and reads the site live; do not copy the artifact into a
   separate hosting repository or start another server. Check the actual access
   plane before sharing a URL. Artoo itself does not add authentication.
5. Record findings and fixes against the rendered revision:

   ```bash
   artoo review path/to/artifact "The mobile answer is below the first screen" --page answers/device-policy/index.html
   artoo review path/to/artifact "Selected answer now receives focus" --page answers/device-policy/index.html --resolves <finding-id>
   ```

   The append-only `work/reviews.jsonl` records event ids, the artifact slug,
   site digest, Git head and dirty state, page, text, timestamp, and the
   finding resolved. Commit those events with the source-owned artifact. A
   resolution points to the earlier finding and captures the *new* render;
   the reviewer can compare both. `--page` must name a served file. The review
   file stays outside `site/` and is never served or deployed.

`artoo feedback` is a different route: when a Flip notebook is attached, it
opens a question or log in that canonical research record. Use it for source
claim corrections. Use `artoo review` for presentation, flow, and acceptance
findings, including artifacts without notebooks. One accountable source owner
accepts a correction; a green browser check does not do that work.

Dirk discovery is a convenience, not a publication or approval gate. Public
deployment still requires its own authorization and `artoo deploy` or the
owning product's publisher. Access controls belong to the existing reader
plane; do not widen them to make review easier.
