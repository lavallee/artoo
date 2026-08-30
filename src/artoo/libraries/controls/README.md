# artoo-controls

The recurring interaction shell for an explorer: search, declared filters,
active chips, a live result count, reset, URL state, CSV download, and optional
named configurations. It works with ordinary arrays and renders from
`file://`; the explorer remains responsible for presenting the filtered rows.

```html
<div id="controls"></div>
<script src="data/items.js"></script>
<script src="lib/artoo-controls/controls.js"></script>
<script>
const controls = ArtooControls.create("#controls", {
  data: window.ARTOO_DATA,
  search: { fields: ["name", "description"], label: "Search" },
  filters: [{ field: "type", label: "Type" }],
  url: true,
  download: "items.csv",
  onChange(rows, state) { render(rows); },
});
</script>
```

Filter options are inferred from the rows unless an `options` array is
declared. Set `multiple: true` for a multiple select. `controls.state()` returns
the current `{q, filters}` value and `controls.setState(value)` restores one.

Set `presets: "collection-name"` to show Save and Load buttons. When
`ArtooStore` is loaded, saves go through `artoo serve` into reviewable
`state/` files; otherwise controls say that presets are unavailable rather
than implying durability they do not have.

URL state uses `history.replaceState`; it never reloads the page. CSV is built
from the filtered rows. Pass `downloadFields` to control its columns.
