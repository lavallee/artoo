# artoo-controls 0.1.0

Search, filter groups, active chips, result counts, URL state, CSV downloads, and optional saved explorer configurations.

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

## Class vocabulary

| class | role |
|---|---|
| `controls` | root enhanced by ArtooControls.create() |
| `controls-bar` | responsive row containing search, filters, and actions |
| `controls-field` | label and input pair |
| `controls-search` | free-text search input |
| `controls-select` | single- or multiple-value filter |
| `controls-actions` | reset, download, and optional preset actions |
| `controls-summary` | live result summary and active filters |
| `controls-count` | aria-live result count |
| `controls-chips` | active-filter list |
| `controls-chip` | button that removes one active filter |
| `controls-reset` | clear-all button |
| `controls-download` | CSV download button |
| `controls-save` | save-current-configuration button |
| `controls-load` | restore-saved-configuration button |
| `controls-status` | preset durability and result feedback |
| `controls-empty` | accessible empty-result message authored by the explorer |

artoo-controls owns `controls-`. A class starting with one of those that the vendored stylesheet does not define is a guess, and `artoo build` reports it with the nearest real class. Your own classes belong outside those prefixes.
