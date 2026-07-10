"""Prompt builders for the explainer pipeline.

Analysis prompts run where the repo is (codex reads files itself inside a
read-only sandbox). Synthesis prompts carry the material inline.
"""

from __future__ import annotations

import json

KIT_VOCABULARY = """\
You write semantic HTML fragments styled by an existing design kit. Use ONLY
these classes (no inline styles, no external resources):

- Layout: the fragment is placed inside <main class="article"> — a grid where
  plain children sit in the prose column. Wrappers: .article-breakout (wider),
  .article-full (edge to edge).
- Header (once, at top): <header class="article-header"> with
  .article-kicker, <h1 class="article-title">, <p class="article-dek">.
- Margin notes: <div class="article-mrow"><p>…paragraph…</p>
  <aside class="article-marginnote article-marginnote--def">
  <span class="term">Term</span> definition…</aside></div>
  Variants: --def (definitions), --source (provenance), --callout.
- Pull quotes: <blockquote class="article-pullquote">…<cite>—…</cite></blockquote>
- Big numbers: <div class="article-pullnumber"><span class="num">19</span>
  <span class="label">schema migrations</span></div>
- Stats: <div class="stat-row"><div class="stat"><span class="value">23k</span>
  <span class="label">source LOC</span></div>…</div>
- Callouts: <div class="callout callout--warn"><span class="callout-title">…
  </span>…</div> (also --success, --danger, or plain).
- Cards: <div class="card-grid"><a class="card" href="page.html"><h3>…</h3>
  <p>…</p></a>…</div>
- Diagrams: <div class="diagram"><pre class="mermaid">…mermaid source…
  </pre></div>
- Code refs: <code>path/to/file.py:123</code>. Tables, pre/code, h2/h3,
  figure/figcaption are all styled — use them plainly.
"""


def analysis_prompt(repo_name: str, unit: dict, readme_hint: str) -> str:
    file_list = "\n".join(f"- {p}" for p in unit["files"][:80])
    more = f"\n(and {len(unit['files']) - 80} more files in the same area)" if len(unit["files"]) > 80 else ""
    return f"""You are analyzing part of the `{repo_name}` repository for a technical
explainer. Repo context: {readme_hint or "(no README summary available)"}

Read the following files (you have read-only access to the repo):
{file_list}{more}

Write a brief in markdown with exactly these sections:

## Purpose
What this area is for, in plain language. 2-4 sentences.

## How it works
The mechanism: key flows, data structures, lifecycle. Cite files as
`path:line` where it matters. 1-3 paragraphs.

## Key surfaces
The entry points someone would actually call/use: functions, classes,
commands. One line each with a `path:line` reference.

## Design decisions
Non-obvious choices and why they seem to have been made (invariants,
trade-offs, defensive patterns). Only real observations — skip if none.

## One-liner
A single sentence summarizing this area.

Be concrete and factual. If something is unclear from the code, say so
rather than guessing. Maximum ~600 words."""


def plan_prompt(inv: dict, briefs: dict[str, str]) -> str:
    brief_text = "\n\n".join(
        f"### Unit: {name}\n{text[:3000]}" for name, text in sorted(briefs.items())
    )
    stats = {
        "name": inv["name"],
        "loc_by_extension": dict(list(inv["loc_by_extension"].items())[:8]),
        "python_source_loc": inv["python"]["source_loc"],
        "python_test_loc": inv["python"]["test_loc"],
        "packages": [p["name"] or p["path"] for p in inv["python"]["packages"]],
        "readme": inv["readme"],
    }
    return f"""You are planning a multi-page HTML explainer for the `{inv["name"]}`
repository. Ground truth stats:

{json.dumps(stats, indent=1)}

Per-area analysis briefs:

{brief_text}

Design a site of 4-7 pages. The first page must have slug "index" (the
overview). Give each page a clear purpose and 3-6 section headings. Prefer
narrative structure (what is this system, how does it work, how do the
pieces fit) over file-by-file listing; one reference-style page is fine.

Return ONLY a JSON object, no prose, shaped exactly like:
{{
  "site_title": "…",
  "tagline": "one sentence",
  "pages": [
    {{"slug": "index", "title": "Overview", "purpose": "…",
      "sections": ["…", "…"]}},
    …
  ]
}}"""


def page_prompt(inv: dict, plan: dict, page: dict, briefs: dict[str, str]) -> str:
    nav = ", ".join(f'{p["slug"]}.html ("{p["title"]}")' for p in plan["pages"])
    brief_text = "\n\n".join(
        f"### {name}\n{text}" for name, text in sorted(briefs.items())
    )
    return f"""{KIT_VOCABULARY}

You are writing ONE page of a multi-page explainer for the `{inv["name"]}`
repository.

Site: {plan.get("site_title", inv["name"])} — {plan.get("tagline", "")}
All pages (for internal links): {nav}

THIS page: slug "{page["slug"]}", title "{page["title"]}".
Purpose: {page["purpose"]}
Planned sections: {json.dumps(page.get("sections", []))}

Source material — per-area analysis briefs (ground truth; do not invent
beyond them):

{brief_text}

Write the HTML fragment for this page's <main class="article"> content:
start with the article-header, then the sections. Use margin notes for
definitions and provenance, a stat-row or pullnumber where a number carries
weight, a mermaid diagram if this page explains structure or flow, and
cards for links to related pages. Cite real files as <code>path:line</code>.
Every factual statement must trace to the briefs or the stats given.

Return ONLY the HTML fragment — no <html>, <head>, <body>, no markdown
fences, no commentary."""
