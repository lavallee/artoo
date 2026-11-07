#!/usr/bin/env python3
"""Render the landing site's Features page from site/landing/work/features.json.

The JSON is the source: everything artoo does, grouped, with how you reach it and the release it arrived in. Other
tools can read it too. The page is rendered with artoo's own Markdown converter, so its tables get the kit's scroll
region and wrapping code, and wrapped in the landing page's shell.

    uv run python scripts/build-features.py      (then: cd site/landing && uv run artoo build .)
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from artoo.generators.notebook_report import markdown

ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "site" / "landing"
data = json.loads((LANDING / "work" / "features.json").read_text(encoding="utf-8"))


def cell(text: str) -> str:
    return text.replace("|", "\\|")


def code(cli: str) -> str:
    return " · ".join(f"`{part.strip()}`" for part in cli.split(" · "))


md = ["Each row says how you reach a feature, as a command or a manifest setting, and the release it arrived in. "
      "Names link to the reference that explains it.", ""]
for group in data["groups"]:
    rows = [f for f in data["features"] if f["group"] == group["id"]]
    md += [f"## {group['name']}", "", "| Feature | What it does | How | Since |", "|---|---|---|---:|"]
    for f in rows:
        # The reference is published from docs/, outside this artifact, so link it where it's served.
        docs = f.get("docs", "")
        url = docs if docs.startswith("http") else f"https://lavallee.github.io/artoo/{docs}"
        name = f"[{f['name']}]({url})" if f.get("docs") else f["name"]
        md.append(f"| {cell(name)} | {cell(f['summary'])} | {cell(code(f['cli'])) if f.get('cli') else '—'} | {f.get('since', '')} |")
    md.append("")
md.append(f"*{len(data['features'])} features, from `site/landing/work/features.json`. The "
          "[changelog](https://github.com/lavallee/artoo/blob/main/CHANGELOG.md) has the detail.*")
body = markdown.to_html("\n".join(md))
body = re.sub(r"<h2>(.*?)</h2>", lambda m: f'<h2 id="{re.sub(r"[^a-z0-9]+", "-", m.group(1).lower()).strip("-")}">{m.group(1)}</h2>', body)

index = (LANDING / "site" / "index.html").read_text(encoding="utf-8")
head = index[: index.index("<main")]
head = re.sub(r"<title>.*?</title>", f"<title>Features — artoo</title>", head, count=1)
head = re.sub(r'<meta name="description" content="[^"]*">',
              f'<meta name="description" content="Everything artoo {data["version"]} does, in one list.">', head, count=1)
toc = "".join(f'<li><a href="#{re.sub(r"[^a-z0-9]+", "-", g["name"].lower()).strip("-")}">{html.escape(g["name"])}</a></li>'
              for g in data["groups"])
page = f"""{head}<main class="article">
  <header class="article-header">
    <div class="article-kicker">Reference</div>
    <h1 class="article-title">Features</h1>
    <p class="article-dek">Everything artoo {html.escape(data["version"])} does: how you reach it, and when it arrived.</p>
  </header>
  <nav class="toc" aria-label="Groups"><ol>{toc}</ol></nav>
{body}
</main>
<script src="lib/artoo-kit/kit.js"></script>
</body>
</html>
"""
(LANDING / "site" / "features.html").write_text(page, encoding="utf-8")
print(f"features.html: {len(data['features'])} features in {len(data['groups'])} groups")
