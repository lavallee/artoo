/* artoo-controls — declared search, filters, URL state, exports, and presets. */
(function (global) {
  "use strict";

  function node(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text != null) el.textContent = text;
    return el;
  }

  function values(rows, field) {
    var seen = {};
    rows.forEach(function (row) {
      var value = row[field];
      if (value != null && value !== "") seen[String(value)] = true;
    });
    return Object.keys(seen).sort(function (a, b) { return a.localeCompare(b); });
  }

  function selected(select) {
    return Array.prototype.filter.call(select.options, function (option) {
      return option.selected && option.value;
    }).map(function (option) { return option.value; });
  }

  function csv(rows, fields) {
    function cell(value) {
      if (value == null) return "";
      var text = String(value);
      return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
    }
    return [fields.map(cell).join(",")].concat(rows.map(function (row) {
      return fields.map(function (field) { return cell(row[field]); }).join(",");
    })).join("\n") + "\n";
  }

  function create(target, options) {
    var root = typeof target === "string" ? document.querySelector(target) : target;
    if (!root) throw new Error("ArtooControls target was not found");
    options = options || {};
    var rows = Array.isArray(options.data) ? options.data.slice() : [];
    var filters = options.filters || [];
    var state = { q: "", filters: {} };
    var inputs = {};
    var current = rows.slice();
    root.classList.add("controls");
    root.textContent = "";

    var bar = node("div", "controls-bar");
    var search = null;
    if (options.search) {
      var searchField = node("label", "controls-field", options.search.label || "Search");
      search = node("input", "controls-search");
      search.type = "search";
      search.placeholder = options.search.placeholder || "Search";
      searchField.appendChild(search);
      bar.appendChild(searchField);
    }
    filters.forEach(function (filter) {
      var field = node("label", "controls-field", filter.label || filter.field);
      var select = node("select", "controls-select");
      select.multiple = !!filter.multiple;
      if (!filter.multiple) select.appendChild(new Option("All", ""));
      (filter.options || values(rows, filter.field)).forEach(function (value) {
        var option = typeof value === "object" ? value : { value: value, label: value };
        select.appendChild(new Option(option.label, option.value));
      });
      field.appendChild(select);
      bar.appendChild(field);
      inputs[filter.field] = select;
    });

    var actions = node("div", "controls-actions");
    var reset = node("button", "controls-reset", "Reset");
    reset.type = "button";
    actions.appendChild(reset);
    var download = null;
    if (options.download) {
      download = node("button", "controls-download", "Download CSV");
      download.type = "button";
      actions.appendChild(download);
    }
    var save = null;
    var load = null;
    var store = options.presets && global.ArtooStore ? global.ArtooStore.open(options.presets) : null;
    if (options.presets) {
      save = node("button", "controls-save", "Save view");
      load = node("button", "controls-load", "Load view");
      save.type = load.type = "button";
      save.disabled = load.disabled = !store;
      actions.appendChild(save);
      actions.appendChild(load);
    }
    bar.appendChild(actions);
    root.appendChild(bar);
    var summary = node("div", "controls-summary");
    var count = node("span", "controls-count");
    count.setAttribute("aria-live", "polite");
    var chips = node("ul", "controls-chips");
    var status = node("span", "controls-status");
    if (options.presets && !store) status.textContent = "Load artoo-kit/store.js to save views.";
    summary.appendChild(count);
    summary.appendChild(chips);
    summary.appendChild(status);
    root.appendChild(summary);

    function read() {
      state.q = search ? search.value.trim() : "";
      state.filters = {};
      filters.forEach(function (filter) {
        var picked = selected(inputs[filter.field]);
        if (picked.length) state.filters[filter.field] = picked;
      });
    }

    function write() {
      if (search) search.value = state.q || "";
      filters.forEach(function (filter) {
        var wanted = state.filters[filter.field] || [];
        Array.prototype.forEach.call(inputs[filter.field].options, function (option) {
          option.selected = wanted.indexOf(option.value) !== -1;
        });
      });
    }

    function urlWrite() {
      if (!options.url || !global.history) return;
      var params = new URLSearchParams(global.location.search);
      params.delete("q");
      filters.forEach(function (filter) { params.delete(filter.field); });
      if (state.q) params.set("q", state.q);
      Object.keys(state.filters).forEach(function (field) {
        state.filters[field].forEach(function (value) { params.append(field, value); });
      });
      var query = params.toString();
      global.history.replaceState(null, "", global.location.pathname + (query ? "?" + query : "") + global.location.hash);
    }

    function urlRead() {
      if (!options.url) return;
      var params = new URLSearchParams(global.location.search);
      state.q = params.get("q") || "";
      filters.forEach(function (filter) {
        var picked = params.getAll(filter.field);
        if (picked.length) state.filters[filter.field] = picked;
      });
    }

    function renderChips() {
      chips.textContent = "";
      if (state.q) addChip("Search: " + state.q, "q", state.q);
      filters.forEach(function (filter) {
        (state.filters[filter.field] || []).forEach(function (value) {
          addChip((filter.label || filter.field) + ": " + value, filter.field, value);
        });
      });
    }

    function addChip(label, field, value) {
      var item = node("li");
      var button = node("button", "controls-chip", label + " ×");
      button.type = "button";
      button.addEventListener("click", function () {
        if (field === "q") state.q = "";
        else state.filters[field] = (state.filters[field] || []).filter(function (v) { return v !== value; });
        write();
        apply();
      });
      item.appendChild(button);
      chips.appendChild(item);
    }

    function apply() {
      read();
      var query = state.q.toLowerCase();
      var searchFields = (options.search && options.search.fields) || Object.keys(rows[0] || {});
      current = rows.filter(function (row) {
        if (query && !searchFields.some(function (field) {
          return String(row[field] == null ? "" : row[field]).toLowerCase().indexOf(query) !== -1;
        })) return false;
        return Object.keys(state.filters).every(function (field) {
          return state.filters[field].indexOf(String(row[field])) !== -1;
        });
      });
      count.textContent = current.length === rows.length ? rows.length + " results" : current.length + " of " + rows.length + " results";
      renderChips();
      urlWrite();
      if (options.onChange) options.onChange(current.slice(), JSON.parse(JSON.stringify(state)));
    }

    if (search) search.addEventListener("input", apply);
    Object.keys(inputs).forEach(function (field) { inputs[field].addEventListener("change", apply); });
    reset.addEventListener("click", function () { state = { q: "", filters: {} }; write(); apply(); });
    if (download) download.addEventListener("click", function () {
      var fields = options.downloadFields || Object.keys(current[0] || rows[0] || {});
      var blob = new Blob([csv(current, fields)], { type: "text/csv;charset=utf-8" });
      var anchor = document.createElement("a");
      anchor.href = URL.createObjectURL(blob);
      anchor.download = typeof options.download === "string" ? options.download : "results.csv";
      anchor.click();
      URL.revokeObjectURL(anchor.href);
    });
    if (save) save.addEventListener("click", function () {
      var name = global.prompt("Name this view");
      if (!name) return;
      store.save(name, state).then(function () { status.textContent = store.describe(); });
    });
    if (load) load.addEventListener("click", function () {
      store.list().then(function (entries) {
        var name = global.prompt("Load which view?\n" + entries.map(function (entry) { return entry.name; }).join("\n"));
        if (!name) return null;
        return store.load(name);
      }).then(function (saved) { if (saved) { state = saved; write(); apply(); } });
    });

    urlRead();
    write();
    apply();
    return {
      rows: function () { return current.slice(); },
      state: function () { return JSON.parse(JSON.stringify(state)); },
      setState: function (next) { state = next || { q: "", filters: {} }; write(); apply(); },
      setData: function (next) { rows = next.slice(); apply(); },
    };
  }

  global.ArtooControls = { create: create, csv: csv };
})(typeof window !== "undefined" ? window : this);
