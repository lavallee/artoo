"""The ``grid`` Markdown block: a dense table bound to a data pack by name.

The table's rows are never written into the page source. The block names a
``[[data]]`` pack and the fields to show; the build checks those fields exist
in the pack, so a renamed column fails the build instead of rendering an
empty one, and no figure is ever retyped by hand from the data.
"""

from __future__ import annotations

import json
from pathlib import Path

from ...blocks import Attr, Block, Call, esc

FORMATS = ("text", "name", "chip", "number", "currency", "percent", "rank", "delta")
_FLAGS = ("bar", "heat", "frozen", "hidden", "invert", "invertHeat")
_KEYS = {"group": str, "decimals": int, "scale": float, "sub": str, "width": int,
         "missingLabel": str}


def _rows(value, key: str):
    if key:
        for part in key.split("."):
            value = value.get(part) if isinstance(value, dict) else None
    return value if isinstance(value, list) else None


def _pack_rows(call: Call, global_name: str, key: str):
    """The pack's rows as the page will see them, or None when they cannot be read."""
    pack = next((p for p in call.ctx.data_packs if p.get("global") == global_name), None)
    if pack is None:
        known = ", ".join(sorted(str(p.get("global")) for p in call.ctx.data_packs)) or "none"
        call.error(
            f"data={global_name!r} names no [[data]] pack (declared globals: {known}); "
            "add a [[data]] entry with global = \"…\" to artifact.toml"
        )
        return None, None
    rows = None
    if call.ctx.artifact_dir is not None:
        try:
            source = Path(call.ctx.artifact_dir) / str(pack.get("source", ""))
            rows = _rows(json.loads(source.read_text(encoding="utf-8")), key)
        except (OSError, ValueError):
            rows = None  # the data step reports unreadable packs itself
        if rows is None:
            where = f"key {key!r} of " if key else ""
            call.error(
                f"{where}pack {global_name!r} is not a list of rows; "
                "point rows= at the array (e.g. rows=items)"
            )
            return pack, None
    return pack, rows


def _column(call: Call, offset: int, line: str, fields: set[str] | None):
    parts = [part.strip() for part in line.split("|")]
    if len(parts) < 2 or not parts[0]:
        call.error(f"column line {line!r} needs `field | Title | format flags…`", offset)
        return None
    spec: dict = {"field": parts[0], "title": parts[1] or parts[0]}
    for token in " ".join(parts[2:]).split():
        if token in FORMATS:
            spec["format"] = token
        elif token in _FLAGS:
            spec[token] = True
        elif "=" in token and token.split("=", 1)[0] in _KEYS:
            key, raw = token.split("=", 1)
            try:
                spec[key] = _KEYS[key](raw)
            except ValueError:
                call.error(f"column {parts[0]!r}: {key}={raw!r} is not a number", offset)
                return None
        else:
            call.error(
                f"column {parts[0]!r}: unknown {token!r}; formats are {', '.join(FORMATS)}, "
                f"flags {', '.join(_FLAGS)}, keys {', '.join(k + '=' for k in _KEYS)}",
                offset,
            )
            return None
    if fields is not None:
        for name in (spec["field"], spec.get("sub")):
            if name and name not in fields:
                sample = ", ".join(sorted(fields)[:12])
                call.error(f"column field {name!r} is not in the data (it has {sample})", offset)
                return None
    return spec


def _grid(call: Call) -> str:
    global_name = call.get("data")
    key = call.get("rows")
    pack, rows = _pack_rows(call, global_name, key)
    if pack is None:
        return ""
    fields = None
    if rows is not None:
        fields = {k for row in rows if isinstance(row, dict) for k in row}
    columns = []
    for offset, line in call.lines():
        spec = _column(call, offset, line, fields)
        if spec is None:
            return ""
        columns.append(spec)
    if not columns:
        call.error("has no columns; write one `field | Title | format` line per column")
        return ""
    index = call.get("index")
    if index and fields is not None and index not in fields:
        call.error(f"index={index!r} is not a field in the data")
        return ""
    script = str(pack.get("script", "")) or str(Path(str(pack.get("path", ""))).with_suffix(".js"))
    call.ctx.need_script(script)
    toolbar: dict = {}
    if call.flag("search"):
        toolbar["search"] = True
    if call.flag("columns"):
        toolbar["columns"] = True
    if call.get("download"):
        toolbar["download"] = call.get("download")
    config: dict = {"columns": columns}
    if index:
        config["index"] = index
    if toolbar:
        config["toolbar"] = toolbar
    if call.get("note"):
        config["note"] = call.get("note")
    mount = f"{call.id}-grid" if call.id else call.ctx.next_id("artoo-grid")
    payload = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
    lookup = json.dumps(key or "")
    caption = call.get("caption")
    figcaption = f"<figcaption>{call.inline(caption)}</figcaption>" if caption else ""
    return (
        f'<figure class="article-figure"><div id="{esc(mount)}"></div>{figcaption}'
        f"<script>document.addEventListener(\"DOMContentLoaded\",function(){{"
        f"var d=window[{json.dumps(global_name)}],k={lookup},c={payload};"
        f"if(k){{k.split('.').forEach(function(p){{d=d&&d[p];}});}}"
        f"c.data=Array.isArray(d)?d:[];ArtooGrid.create({json.dumps('#' + mount)},c);}});"
        f"</script></figure>"
    )


BLOCKS = (
    Block(
        name="grid",
        library="artoo-grid",
        summary=(
            "a sortable dense table bound to a [[data]] pack; one `field | Title | format flags` "
            "line per column. Fields are checked against the pack at build time"
        ),
        render=_grid,
        attrs=(
            Attr("data", "the [[data]] pack's global name", required=True),
            Attr("rows", "dotted key of the row array inside the pack, if it is not the root"),
            Attr("index", "field that identifies a row"),
            Attr("search", "show the free-text filter", flag=True),
            Attr("columns", "show the column picker", flag=True),
            Attr("download", "CSV filename for the export button"),
            Attr("note", "footer: vintage, denominator, source"),
            Attr("caption", "figure caption under the table"),
        ),
        body="lines",
        styles=("lib/artoo-grid/tabulator.min.css", "lib/artoo-grid/grid.css"),
        scripts=("lib/artoo-grid/tabulator.min.js", "lib/artoo-grid/grid.js"),
        example=(
            '::: grid data=DISTRICTS index=id search columns download=districts.csv '
            'note="ACS 2020–2024"\n'
            "name | District | name frozen sub=county\n"
            "hhi | Median household income | currency bar\n"
            "prof | Proficient | percent heat decimals=1\n:::"
        ),
    ),
)
