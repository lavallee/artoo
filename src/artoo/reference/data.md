# Deterministic data packing

Explorers repeatedly need one canonical JSON file plus a JavaScript global that
works from `file://`, where fetching a sibling file is blocked. Declare that
join once:

```toml
[[data]]
source = "work/items.json"
path = "data/items.json"
script = "data/items.js"
global = "ARTOO_DATA"
```

`artoo build` validates the source, writes pretty canonical JSON under `site/`,
and writes the sibling loader as `window.ARTOO_DATA = …`. The source can stay
behind the firewall; both generated outputs are deterministic. Omit `script`
to derive it from `path` by replacing the suffix with `.js`.

Every destination must remain under `build.site`, and the global must be a
plain JavaScript identifier. Multiple `[[data]]` entries are allowed.

Use `artoo-controls` for recurring search/filter/download behavior and
`artoo-grid` for dense analytical tables. Neither owns the data preparation;
build commands can refresh `work/items.json` first, then the packer publishes
the exact result.
