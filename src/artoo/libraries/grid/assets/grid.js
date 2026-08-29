/* artoo-grid — declarative data tables over the vendored Tabulator build.
 *
 * The problem this solves: a comparison table of a few hundred rows and a few
 * dozen measures is a normal artefact of analytical work, and hand-rolling one
 * costs the same two days every time — sorting, sticky identity columns, a
 * column picker, number formats that line up, an export, and a way to say
 * "this value is missing" that does not read as "this value is zero".
 *
 * So a grid is declared, not assembled:
 *
 *   ArtooGrid.create("#table", {
 *     data: rows,
 *     index: "id",
 *     columns: [
 *       { field: "rank",  title: "#",        format: "rank",  frozen: true, width: 52 },
 *       { field: "name",  title: "District", format: "name",  frozen: true, sub: "county" },
 *       { field: "hhi",   title: "Median household income",
 *         group: "Means", format: "currency", bar: true },
 *       { field: "prof",  title: "Proficient",
 *         group: "Achievement", format: "percent", heat: true, decimals: 1 },
 *       { field: "move",  title: "Δ rank",   format: "delta", invert: true },
 *     ],
 *     toolbar: { search: true, columns: true, download: "districts.csv" },
 *     note: "ACS 2020-2024 · NJDOE 2024-25 · missing values shown as —, never as 0",
 *   });
 *
 * Formats carry the editorial rules, which is the point of having them:
 *
 *   number   right-aligned tabular figures, thousands separated
 *   currency whole dollars, no cents, `$` only in the header if you want one
 *   percent  a value already on 0-100, or set `scale: 100` for a 0-1 fraction
 *   rank     bold ordinal; ties are the caller's problem, not the grid's
 *   delta    signed, coloured by direction (Okabe-Ito blue/orange, not red/green)
 *   name     primary label with an optional smaller `sub` field beneath it
 *   chip     a short categorical label in a pill
 *   text     left-aligned prose
 *
 * `bar: true` lays a proportional background behind a numeric cell and `heat:
 * true` tints it by percentile. Both derive their domain from the data each
 * time it is set, so a filtered or recomputed table rescales honestly instead
 * of comparing today's numbers against yesterday's maximum.
 *
 * Null, undefined and NaN all render as an em dash in the missing style. That
 * is deliberate and not configurable: a grid that lets a caller print 0 for a
 * value nobody measured is a grid that will eventually do it by accident.
 */
(function (global) {
  "use strict";

  var NBSP = " ";
  var DASH = "—";

  function isNil(v) {
    return v === null || v === undefined || v === "" || (typeof v === "number" && !isFinite(v));
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function missing(label) {
    var s = el("span", "grid-num grid-missing");
    s.textContent = label || DASH;
    return s;
  }

  function fmtNumber(v, decimals) {
    return v.toLocaleString(undefined, {
      minimumFractionDigits: decimals || 0,
      maximumFractionDigits: decimals || 0,
    });
  }

  /* Domains are recomputed on every setData. A bar whose scale is stale is
     worse than no bar: it looks like a measurement and is an artefact. */
  function computeDomain(rows, field, opts) {
    var lo = Infinity;
    var hi = -Infinity;
    var vals = [];
    for (var i = 0; i < rows.length; i++) {
      var v = rows[i][field];
      if (isNil(v) || typeof v !== "number") continue;
      vals.push(v);
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    if (!vals.length) return { lo: 0, hi: 1, sorted: [] };
    vals.sort(function (a, b) { return a - b; });
    if (opts && opts.zeroBased && lo > 0) lo = 0;
    if (lo === hi) hi = lo + 1;
    return { lo: lo, hi: hi, sorted: vals };
  }

  /* Percentile of v within an ascending array, by binary search. Used for the
     heat tint so that a handful of extreme values cannot flatten the rest of
     the column into one indistinguishable shade. */
  function percentile(sorted, v) {
    if (!sorted.length) return 0;
    var lo = 0;
    var hi = sorted.length;
    while (lo < hi) {
      var mid = (lo + hi) >> 1;
      if (sorted[mid] < v) lo = mid + 1; else hi = mid;
    }
    return lo / (sorted.length - 1 || 1);
  }

  var FORMATTERS = {
    text: function (v) { return el("span", null, String(v)); },

    chip: function (v) { return el("span", "grid-chip", String(v)); },

    name: function (v, spec, row) {
      var wrap = document.createDocumentFragment();
      var main = el("span", "grid-name", String(v));
      wrap.appendChild(main);
      if (spec.sub && !isNil(row[spec.sub])) {
        wrap.appendChild(el("span", "grid-sub", String(row[spec.sub])));
      }
      return wrap;
    },

    number: function (v, spec) {
      return el("span", "grid-num", fmtNumber(v, spec.decimals));
    },

    currency: function (v, spec) {
      var d = spec.decimals || 0;
      return el("span", "grid-num", "$" + fmtNumber(v, d));
    },

    percent: function (v, spec) {
      var scaled = spec.scale ? v * spec.scale : v;
      var d = spec.decimals === undefined ? 1 : spec.decimals;
      return el("span", "grid-num", fmtNumber(scaled, d) + "%");
    },

    rank: function (v, spec) {
      return el("span", "grid-rank", fmtNumber(v, spec.decimals));
    },

    delta: function (v, spec) {
      var d = spec.decimals || 0;
      var s = el("span", "grid-delta");
      var sign = v > 0 ? "pos" : v < 0 ? "neg" : "zero";
      /* `invert` is for the columns where up is bad — a rank that rises is a
         district that fell. The colour follows meaning, never arithmetic. */
      if (spec.invert && sign !== "zero") sign = sign === "pos" ? "neg" : "pos";
      s.dataset.sign = sign;
      s.textContent = (v > 0 ? "+" : v < 0 ? "−" : NBSP) + fmtNumber(Math.abs(v), d);
      return s;
    },
  };

  function decorate(node, v, spec, domain) {
    if (spec.bar && domain) {
      node.classList.remove("grid-num");
      node.classList.add("grid-bar");
      var span = domain.hi - domain.lo || 1;
      var pct = Math.max(0, Math.min(1, (v - domain.lo) / span));
      node.style.setProperty("--grid-fill", (pct * 100).toFixed(2) + "%");
      if (v < 0) node.dataset.sign = "neg";
    }
    if (spec.heat && domain) {
      node.classList.remove("grid-num");
      node.classList.add("grid-heat");
      var p = percentile(domain.sorted, v);
      if (spec.invertHeat) p = 1 - p;
      node.style.setProperty("--grid-alpha", (0.06 + p * 0.34).toFixed(3));
    }
    return node;
  }

  function Grid(mount, config) {
    this.config = config || {};
    this.columns = (this.config.columns || []).map(function (c) {
      return Object.assign({ format: "text" }, c);
    });
    this.rows = this.config.data || [];
    this.domains = {};
    this._build(mount);
  }

  Grid.prototype._build = function (mount) {
    var self = this;
    var host = typeof mount === "string" ? document.querySelector(mount) : mount;
    if (!host) throw new Error("artoo-grid: mount element not found: " + mount);
    host.classList.add("grid");
    host.innerHTML = "";
    this.host = host;

    this._recomputeDomains();

    if (this.config.toolbar !== false) this._buildToolbar(host);

    var body = el("div", "grid-body");
    host.appendChild(body);

    if (this.config.note) {
      var note = el("div", "grid-note");
      note.innerHTML = this.config.note;
      host.appendChild(note);
    }

    this.table = new global.Tabulator(body, Object.assign({
      data: this.rows,
      index: this.config.index,
      columns: this._tabulatorColumns(),
      layout: this.config.layout || "fitDataStretch",
      height: this.config.height || "70vh",
      /* The virtual DOM is what keeps 600 rows x 40 columns interactive; the
         buffer is generous because these tables are read by scrolling fast. */
      renderVerticalBuffer: 600,
      placeholder: this.config.placeholder || "No rows match the current filters.",
      columnDefaults: { headerHozAlign: "left", resizable: true, headerTooltip: true },
      initialSort: this.config.sort || [],
      rowHeader: false,
    }, this.config.tabulator || {}));

    this.table.on("dataFiltered", function (filters, rows) { self._setCount(rows.length); });
    this.table.on("tableBuilt", function () { self._setCount(self.rows.length); });
    if (this.config.onRowClick) {
      this.table.on("rowClick", function (e, row) { self.config.onRowClick(row.getData(), row); });
    }
  };

  Grid.prototype._recomputeDomains = function () {
    var self = this;
    this.columns.forEach(function (spec) {
      if (!spec.bar && !spec.heat) return;
      self.domains[spec.field] = computeDomain(self.rows, spec.field, {
        zeroBased: spec.bar && spec.zeroBased !== false,
      });
    });
  };

  Grid.prototype._tabulatorColumns = function () {
    var self = this;
    var out = [];
    var groups = {};

    this.columns.forEach(function (spec) {
      var def = {
        title: spec.title || spec.field,
        field: spec.field,
        visible: spec.hidden !== true,
        frozen: spec.frozen === true,
        width: spec.width,
        minWidth: spec.minWidth || 56,
        hozAlign: spec.format === "text" || spec.format === "name" || spec.format === "chip" ? "left" : "right",
        headerHozAlign: spec.format === "text" || spec.format === "name" || spec.format === "chip" ? "left" : "right",
        sorter: spec.sorter || (FORMATTERS[spec.format] && spec.format !== "text" && spec.format !== "name" && spec.format !== "chip" ? "number" : "string"),
        headerTooltip: spec.tooltip || spec.title || spec.field,
        /* Blanks sort to the bottom in both directions: a district with no
           measurement has not "scored zero" and must never top a ranking. */
        sorterParams: Object.assign({ alignEmptyValues: "bottom" }, spec.sorterParams || {}),
        formatter: function (cell) {
          var v = cell.getValue();
          var row = cell.getRow().getData();
          if (isNil(v)) return missing(spec.missingLabel || (row[spec.field + "_state"] === "suppressed" ? "suppressed" : DASH));
          var fn = FORMATTERS[spec.format] || FORMATTERS.text;
          var node = fn(v, spec, row);
          if (node.nodeType === 11) return node; // fragment: name format
          return decorate(node, v, spec, self.domains[spec.field]);
        },
      };
      if (spec.group) {
        if (!groups[spec.group]) {
          groups[spec.group] = { title: spec.group, columns: [] };
          out.push(groups[spec.group]);
        }
        groups[spec.group].columns.push(def);
      } else {
        out.push(def);
      }
    });
    return out;
  };

  Grid.prototype._buildToolbar = function (host) {
    var self = this;
    var t = this.config.toolbar || {};
    var bar = el("div", "grid-toolbar");

    this.countEl = el("span", "grid-count", "");
    bar.appendChild(this.countEl);

    if (t.search !== false) {
      var search = el("input", "grid-search");
      search.type = "search";
      search.placeholder = t.searchPlaceholder || "Filter…";
      search.setAttribute("aria-label", t.searchPlaceholder || "Filter rows");
      var fields = t.searchFields || this.columns.filter(function (c) {
        return c.format === "text" || c.format === "name" || c.format === "chip";
      }).map(function (c) { return c.field; });
      search.addEventListener("input", function () {
        var q = search.value.trim().toLowerCase();
        if (!q) { self.table.clearFilter(); return; }
        self.table.setFilter(function (row) {
          for (var i = 0; i < fields.length; i++) {
            var v = row[fields[i]];
            if (v !== null && v !== undefined && String(v).toLowerCase().indexOf(q) !== -1) return true;
          }
          return false;
        });
      });
      bar.appendChild(search);
    }

    if (t.columns !== false) bar.appendChild(this._buildPicker());

    if (t.download) {
      var dl = el("button", "grid-btn", "Download CSV");
      dl.type = "button";
      dl.addEventListener("click", function () {
        self.table.download("csv", typeof t.download === "string" ? t.download : "table.csv");
      });
      bar.appendChild(dl);
    }

    (t.extra || []).forEach(function (node) { bar.appendChild(node); });

    host.appendChild(bar);
  };

  Grid.prototype._buildPicker = function () {
    var self = this;
    var wrap = el("span", "grid-picker");
    var btn = el("button", "grid-btn", "Columns");
    btn.type = "button";
    btn.setAttribute("aria-expanded", "false");
    var menu = el("div", "grid-picker-menu");
    menu.hidden = true;

    var lastGroup = null;
    this.columns.forEach(function (spec) {
      if (spec.frozen) return; // identity columns are not hideable
      if (spec.group && spec.group !== lastGroup) {
        menu.appendChild(el("div", "grid-picker-group", spec.group));
        lastGroup = spec.group;
      }
      var label = el("label");
      var box = el("input");
      box.type = "checkbox";
      box.checked = spec.hidden !== true;
      box.addEventListener("change", function () {
        if (box.checked) self.table.showColumn(spec.field);
        else self.table.hideColumn(spec.field);
      });
      label.appendChild(box);
      label.appendChild(el("span", null, spec.title || spec.field));
      menu.appendChild(label);
    });

    btn.addEventListener("click", function () {
      var open = menu.hidden;
      menu.hidden = !open;
      btn.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("click", function (e) {
      if (!wrap.contains(e.target) && !menu.hidden) {
        menu.hidden = true;
        btn.setAttribute("aria-expanded", "false");
      }
    });

    wrap.appendChild(btn);
    wrap.appendChild(menu);
    this.pickerMenu = menu;
    return wrap;
  };

  Grid.prototype._setCount = function (n) {
    if (!this.countEl) return;
    var total = this.rows.length;
    var noun = this.config.rowNoun || "row";
    var label = n === total
      ? fmtNumber(total) + " " + noun + (total === 1 ? "" : "s")
      : fmtNumber(n) + " of " + fmtNumber(total) + " " + noun + "s";
    this.countEl.textContent = label;
  };

  /* Replace the data and rescale every derived visual. Callers reranking on a
     weight change should use this rather than Tabulator's setData directly. */
  Grid.prototype.setData = function (rows) {
    this.rows = rows || [];
    this._recomputeDomains();
    var self = this;
    return this.table.replaceData(this.rows).then(function () {
      self.table.redraw(true);
      self._setCount(self.table.getDataCount("active"));
    });
  };

  /* Update in place without losing scroll position or sort — the path a live
     reranking slider takes, where a full replaceData would jump the viewport. */
  Grid.prototype.updateRows = function (rows) {
    this.rows = rows || this.rows;
    this._recomputeDomains();
    return this.table.updateData(rows);
  };

  Grid.prototype.setColumnVisible = function (field, visible) {
    if (visible) this.table.showColumn(field); else this.table.hideColumn(field);
    if (this.pickerMenu) {
      var boxes = this.pickerMenu.querySelectorAll("input[type=checkbox]");
      var idx = 0;
      this.columns.forEach(function (spec) {
        if (spec.frozen) return;
        if (spec.field === field && boxes[idx]) boxes[idx].checked = visible;
        idx += 1;
      });
    }
  };

  Grid.prototype.sortBy = function (field, dir) {
    this.table.setSort(field, dir || "desc");
  };

  var ArtooGrid = {
    create: function (mount, config) { return new Grid(mount, config); },
    formatters: FORMATTERS,
    version: "0.1.0",
  };

  if (typeof module === "object" && module.exports) module.exports = ArtooGrid;
  global.ArtooGrid = ArtooGrid;
})(typeof window !== "undefined" ? window : this);
