# Verification

`artoo build` runs static verification after rendering content, packing data,
and projecting evidence. `artoo verify` runs it without changing the artifact.

Hard failures cover:

- missing HTML or CSS assets and internal pages;
- broken fragment anchors and duplicate IDs;
- references that escape `build.site` or target a firewall-withheld path;
- root-relative paths that fail from `file://`;
- remote scripts, styles, fonts, images, and other runtime dependencies;
- literal remote CSS imports or JavaScript fetch/import calls.

Warnings identify images without `alt`, tables without headings or with uneven
row widths, and empty or nowhere-pointing controls. They are review prompts,
not taste scores, and do not fail a build.

## Optional browser proof

```bash
artoo verify path/to/artifact --browser
artoo verify path/to/artifact --browser --screenshots work/verification
```

Browser verification is a soft Playwright integration. When requested, it
firewall-stages the site, opens every publishable page in Chromium at phone and
desktop widths, reports page and console errors, checks horizontal overflow,
and optionally records full-page screenshots. Core Artoo does not depend on Playwright; if it is absent the
command names the install needed or lets you omit `--browser`.

A clean check proves structural and runtime integrity. It does not promote an
artifact's status or establish factual, editorial, visual, or human acceptance.
