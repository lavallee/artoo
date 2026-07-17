"""Prompt builders for the explainer pipeline.

Analysis prompts run where the repo is (codex reads files itself inside a
read-only sandbox). Synthesis prompts carry the material inline.
"""

from __future__ import annotations

import json

KIT_VOCABULARY = """\
You write light, editorial HTML fragments governed by the DES public-artifact
contract and styled by an existing design kit. Use ONLY these classes (no
inline styles, no external resources):

- Layout: the fragment is placed inside <main class="article"> — a grid where
  plain children sit in the prose column. Wrappers: .article-breakout (wider),
  .article-full (edge to edge).
- Header (once, at top): <header class="article-header"> with
  .article-kicker, <h1 class="article-title">, <p class="article-dek">.
- Margin notes: <div class="article-mrow"><p>…paragraph…</p>
  <aside class="article-marginnote article-marginnote--def">
  <span class="term">Term</span> definition…</aside></div>
  Variants: --def (definitions), --source (provenance), --callout.
- Evidence: <figure class="article-figure"> containing a semantic table or
  figure, followed by <figcaption> with units, vintage, denominator, source,
  and limits where relevant. Plain tables also work in the prose column.
- Diagrams: <div class="diagram"><pre class="mermaid">…mermaid source…
  </pre></div>
- Semantic notices: <div class="callout callout--warn"><span
  class="callout-title">…</span>…</div> only for a real warning, success, or
  danger state; status colors are not decoration.
- Cards are available only for true navigation between distinct pages. Never
  turn related facts, sources, or sections into cards.
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

Begin the plan by naming the reader decision: who must decide what after
reading? State one headline claim the evidence can support. Record the
evidence limits and strongest plausible counter-reading. Name only licit
comparisons: axes whose units, vintages, denominators, and scope make the
comparison valid. Select a table, figure, or prose treatment only when that
form directly helps the reader make one of those comparisons; do not choose a
form merely because the kit has a component for it.

Then design a site of 4-7 pages. The first page must have slug "index" (the
overview). Give each page a clear purpose and 3-6 section headings. Prefer a
long-form narrative (claim, mechanism, evidence, limits, implication) over a
dashboard shell or file-by-file listing; one reference-style page is fine.

Return ONLY a JSON object, no prose, shaped exactly like:
{{
  "site_title": "…",
  "tagline": "one sentence",
  "reader_decision": "named reader and concrete decision",
  "headline_claim": "one supportable claim",
  "evidence_limits": ["…"],
  "counter_reading": "strongest plausible alternative reading",
  "licit_comparisons": ["axis, units, vintage, denominator, and scope"],
  "selected_forms": [
    {{"comparison": "…", "form": "table, figure, or prose", "reason": "reader benefit"}}
  ],
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

Reader decision: {plan.get("reader_decision", "Not supplied; state it conservatively from the evidence.")}
Headline claim: {plan.get("headline_claim", "Not supplied; do not invent one.")}
Evidence limits: {json.dumps(plan.get("evidence_limits", []))}
Counter-reading: {plan.get("counter_reading", "Not supplied; identify the strongest evidence-based limit.")}
Licit comparisons: {json.dumps(plan.get("licit_comparisons", []))}
Selected forms and reasons: {json.dumps(plan.get("selected_forms", []))}

Source material — per-area analysis briefs (ground truth; do not invent
beyond them):

{brief_text}

Write the HTML fragment for this page's <main class="article"> content. Begin
from the named reader decision and headline claim: the header states the claim,
the deck says why it matters, and the sections move through evidence, limits or
counter-reading, and implication. Choose a table or figure because it supports
a licit reader comparison, and state its basis and limits in the caption. Do
not detach important numbers into a dashboard-like metric wall. Use cards only
for true navigation, never as the default container for related items. Use
margin notes for definitions and file-level provenance. Cite real files as
<code>path:line</code>. Every factual statement must trace to the briefs or the
inventory stats given.

Return ONLY the HTML fragment — no <html>, <head>, <body>, no markdown
fences, no commentary."""
