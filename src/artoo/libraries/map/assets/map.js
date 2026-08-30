/* artoo-map — bounded interactive projections over artoo-codegraph/1. */
(function (global) {
  "use strict";

  var TRUTHS = ["declared", "static", "runtime", "inferred"];

  function node(tag, cls, text) {
    var element = document.createElement(tag);
    if (cls) element.className = cls;
    if (text != null) element.textContent = text;
    return element;
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function download(name, text, type) {
    var blob = new Blob([text], { type: type || "text/plain;charset=utf-8" });
    var anchor = document.createElement("a");
    anchor.href = URL.createObjectURL(blob);
    anchor.download = name;
    anchor.click();
    URL.revokeObjectURL(anchor.href);
  }

  function indexGraph(graph) {
    var nodes = {};
    var outgoing = {};
    var incoming = {};
    graph.nodes.forEach(function (item) {
      nodes[item.id] = item;
      outgoing[item.id] = [];
      incoming[item.id] = [];
    });
    graph.edges.forEach(function (edge) {
      if (outgoing[edge.source]) outgoing[edge.source].push(edge);
      if (incoming[edge.target]) incoming[edge.target].push(edge);
    });
    return { nodes: nodes, outgoing: outgoing, incoming: incoming };
  }

  function definition(graph, name) {
    return graph.views.filter(function (view) { return view.id === name; })[0] || graph.views[0];
  }

  function resolve(graph, value) {
    if (!value) return null;
    var folded = value.toLowerCase();
    var exact = graph.nodes.filter(function (item) {
      return item.id === value || item.path === value || item.label === value ||
        ((item.attributes || {}).qualified_name === value);
    });
    if (exact.length === 1) return exact[0];
    var partial = graph.nodes.filter(function (item) {
      return item.label.toLowerCase().indexOf(folded) !== -1 ||
        String(item.path || "").toLowerCase().indexOf(folded) !== -1 ||
        String((item.attributes || {}).qualified_name || "").toLowerCase().indexOf(folded) !== -1;
    });
    return partial.length === 1 ? partial[0] : null;
  }

  function priority(item, invoked) {
    if (item.kind === "repository") return 0;
    if (item.kind === "entrypoint") return 1;
    if (item.kind === "package") return 2;
    if (invoked[item.id]) return 3;
    if (item.kind === "module") return 4;
    if (item.kind === "external" && (item.attributes || {}).scope === "third_party") return 5;
    if (item.kind === "service" || item.kind === "datastore") return 6;
    if (item.kind === "class" || item.kind === "function") return 7;
    return 8;
  }

  function project(graph, state, indexes, forced) {
    var view = definition(graph, state.view);
    var layers = state.layers;
    var edgeKinds = view.edge_kinds || null;
    var edges = graph.edges.filter(function (edge) {
      return layers[edge.truth] && (!edgeKinds || edgeKinds.indexOf(edge.kind) !== -1);
    });
    var selected = [];
    var seen = {};
    if (forced && forced.length) {
      selected = forced.slice();
    } else if (state.focus && indexes.nodes[state.focus]) {
      selected.push(state.focus);
      seen[state.focus] = true;
      var queue = [{ id: state.focus, distance: 0 }];
      while (queue.length && selected.length < state.budget) {
        var current = queue.shift();
        if (current.distance >= state.depth) continue;
        var adjacent = [];
        if (state.direction === "outgoing" || state.direction === "both") {
          adjacent = adjacent.concat(indexes.outgoing[current.id]);
        }
        if (state.direction === "incoming" || state.direction === "both") {
          adjacent = adjacent.concat(indexes.incoming[current.id]);
        }
        adjacent.filter(function (edge) {
          return layers[edge.truth] && (!edgeKinds || edgeKinds.indexOf(edge.kind) !== -1);
        }).sort(function (a, b) { return a.id.localeCompare(b.id); }).forEach(function (edge) {
          var next = edge.source === current.id ? edge.target : edge.source;
          if (!seen[next] && selected.length < state.budget) {
            seen[next] = true;
            selected.push(next);
            queue.push({ id: next, distance: current.distance + 1 });
          }
        });
      }
    } else {
      var invoked = {};
      edges.forEach(function (edge) {
        if (edge.kind === "invokes") { invoked[edge.source] = true; invoked[edge.target] = true; }
      });
      var degree = {};
      if (edgeKinds) {
        edges.forEach(function (edge) {
          degree[edge.source] = (degree[edge.source] || 0) + 1;
          degree[edge.target] = (degree[edge.target] || 0) + 1;
        });
      }
      selected = graph.nodes.filter(function (item) {
        return layers[item.truth] && (!edgeKinds || degree[item.id]);
      })
        .sort(function (a, b) {
          if (edgeKinds) {
            return (a.kind === "entrypoint" ? 0 : 1) - (b.kind === "entrypoint" ? 0 : 1) ||
              degree[b.id] - degree[a.id] || a.id.localeCompare(b.id);
          }
          return priority(a, invoked) - priority(b, invoked) || a.id.localeCompare(b.id);
        }).slice(0, state.budget).map(function (item) { return item.id; });
    }
    var selectedSet = {};
    selected.forEach(function (id) { selectedSet[id] = true; });
    var nodes = graph.nodes.filter(function (item) { return selectedSet[item.id]; });
    edges = edges.filter(function (edge) { return selectedSet[edge.source] && selectedSet[edge.target]; });
    return { nodes: nodes, edges: edges, view: view };
  }

  function mermaid(current) {
    var ids = {};
    var lines = ["flowchart LR"];
    current.nodes.forEach(function (item, index) {
      ids[item.id] = "n" + index;
      var label = item.label.replace(/"/g, "'").replace(/\n/g, " ");
      var shape = item.kind === "external" ? '(["' + label + '"])' :
        item.kind === "entrypoint" ? '{{"' + label + '"}}' : '["' + label + '"]';
      lines.push("  " + ids[item.id] + shape);
      lines.push("  class " + ids[item.id] + " truth-" + item.truth);
    });
    current.edges.forEach(function (edge) {
      var arrow = edge.truth === "inferred" ? " -.->|" : " -->|";
      lines.push("  " + ids[edge.source] + arrow + edge.kind.replace(/_/g, " ") + "| " + ids[edge.target]);
    });
    lines.push("  classDef truth-declared stroke:#3e63b4,stroke-width:2px");
    lines.push("  classDef truth-static stroke:#4a5264");
    lines.push("  classDef truth-runtime stroke:#277553,stroke-width:2px");
    lines.push("  classDef truth-inferred stroke:#8a5a00,stroke-dasharray:5 4");
    return lines.join("\n") + "\n";
  }

  function svg(current, cy) {
    var box = cy.extent();
    var width = Math.max(800, Math.ceil(box.w + 80));
    var height = Math.max(500, Math.ceil(box.h + 80));
    function escape(value) {
      return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
    }
    var parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height + '">'];
    parts.push('<rect width="100%" height="100%" fill="#faf7f2"/>');
    current.edges.forEach(function (edge) {
      var source = cy.getElementById(edge.source).renderedPosition();
      var target = cy.getElementById(edge.target).renderedPosition();
      var dash = edge.truth === "inferred" ? ' stroke-dasharray="6 4"' : "";
      parts.push('<line x1="' + source.x + '" y1="' + source.y + '" x2="' + target.x + '" y2="' + target.y + '" stroke="#687080" stroke-width="1.5"' + dash + '/>');
    });
    current.nodes.forEach(function (item) {
      var position = cy.getElementById(item.id).renderedPosition();
      parts.push('<rect x="' + (position.x - 55) + '" y="' + (position.y - 18) + '" width="110" height="36" rx="5" fill="#fff" stroke="#4a5264"/>');
      parts.push('<text x="' + position.x + '" y="' + (position.y + 4) + '" text-anchor="middle" font-family="system-ui,sans-serif" font-size="11" fill="#1f2430">' + escape(item.label.slice(0, 28)) + '</text>');
    });
    parts.push("</svg>");
    return parts.join("");
  }

  function create(target, options) {
    var root = typeof target === "string" ? document.querySelector(target) : target;
    if (!root) throw new Error("ArtooMap target was not found");
    if (!global.cytoscape) throw new Error("ArtooMap requires cytoscape.min.js before map.js");
    options = options || {};
    var graph = options.graph;
    if (!graph || graph.contract !== "artoo-codegraph/1") {
      throw new Error("ArtooMap requires an artoo-codegraph/1 document");
    }
    var indexes = indexGraph(graph);
    var initial = definition(graph, options.view || "overview");
    var state = {
      view: initial.id,
      focus: "",
      direction: initial.direction || "both",
      depth: initial.depth == null ? 2 : initial.depth,
      budget: options.budget || initial.budget || 80,
      layers: {},
    };
    (initial.layers || TRUTHS).forEach(function (truth) { state.layers[truth] = true; });
    var forced = null;
    var current = { nodes: [], edges: [] };
    root.classList.add("map");
    root.textContent = "";

    var datalist = node("datalist");
    datalist.id = "map-node-options-" + Math.random().toString(36).slice(2);
    graph.nodes.forEach(function (item) {
      var option = node("option");
      option.value = item.id;
      option.label = item.label + (item.path ? " — " + item.path : "");
      datalist.appendChild(option);
    });
    root.appendChild(datalist);

    var toolbar = node("div", "map-toolbar");
    function field(label, control) {
      var wrapper = node("label", "map-field", label);
      wrapper.appendChild(control);
      toolbar.appendChild(wrapper);
      return control;
    }
    var viewSelect = node("select", "map-select");
    graph.views.forEach(function (view) { viewSelect.appendChild(new Option(view.id, view.id)); });
    viewSelect.value = state.view;
    field("Saved view", viewSelect);
    var focusInput = node("input", "map-search");
    focusInput.type = "search";
    focusInput.placeholder = "Node id, path, or unique label";
    focusInput.setAttribute("list", datalist.id);
    field("Focus", focusInput);
    var directionSelect = node("select", "map-select");
    ["both", "outgoing", "incoming"].forEach(function (value) { directionSelect.appendChild(new Option(value, value)); });
    directionSelect.value = state.direction;
    field("Direction", directionSelect);
    var depthSelect = node("select", "map-select");
    [0, 1, 2, 3, 4, 5].forEach(function (value) { depthSelect.appendChild(new Option(String(value), String(value))); });
    depthSelect.value = String(state.depth);
    field("Depth", depthSelect);
    var pathFrom = node("input", "map-search");
    pathFrom.type = "search";
    pathFrom.placeholder = "Path from";
    pathFrom.setAttribute("list", datalist.id);
    field("Path from", pathFrom);
    var pathTo = node("input", "map-search");
    pathTo.type = "search";
    pathTo.placeholder = "Path to";
    pathTo.setAttribute("list", datalist.id);
    field("Path to", pathTo);

    var layerSet = node("fieldset", "map-layers");
    var legend = node("legend", "map-field", "Truth layers");
    layerSet.appendChild(legend);
    var layerInputs = {};
    TRUTHS.forEach(function (truth) {
      var label = node("label", "map-layer");
      var input = node("input");
      input.type = "checkbox";
      input.checked = !!state.layers[truth];
      label.appendChild(input);
      label.appendChild(document.createTextNode(truth));
      layerSet.appendChild(label);
      layerInputs[truth] = input;
    });
    toolbar.appendChild(layerSet);

    var actions = node("div", "map-actions");
    function action(label) {
      var button = node("button", "map-button", label);
      button.type = "button";
      actions.appendChild(button);
      return button;
    }
    var pathButton = action("Show path");
    var resetButton = action("Reset");
    var jsonButton = action("JSON");
    var mermaidButton = action("Mermaid");
    var svgButton = action("SVG");
    toolbar.appendChild(actions);
    root.appendChild(toolbar);
    var status = node("div", "map-status");
    status.setAttribute("aria-live", "polite");
    root.appendChild(status);
    var stage = node("div", "map-stage");
    var canvas = node("div", "map-canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", "Code graph; use the table below for keyboard navigation");
    var detail = node("aside", "map-detail");
    detail.setAttribute("aria-live", "polite");
    stage.appendChild(canvas);
    stage.appendChild(detail);
    root.appendChild(stage);
    var fallback = node("details", "map-fallback");
    fallback.appendChild(node("summary", "", "Accessible node list"));
    var table = node("table", "map-table");
    fallback.appendChild(table);
    root.appendChild(fallback);

    var styles = getComputedStyle(root);
    function color(name, fallbackColor) { return styles.getPropertyValue(name).trim() || fallbackColor; }
    var cy = global.cytoscape({
      container: canvas,
      elements: [],
      wheelSensitivity: 0.22,
      minZoom: 0.2,
      maxZoom: 2.5,
      style: [
        { selector: "node", style: {
          "background-color": color("--surface", "#fff"),
          "border-color": color("--muted", "#4a5264"),
          "border-width": 1.5,
          "color": color("--text", "#1f2430"),
          "font-family": color("--font-ui", "system-ui"),
          "font-size": 11,
          "label": "data(label)",
          "shape": "round-rectangle",
          "text-max-width": 115,
          "text-wrap": "ellipsis",
          "width": 122,
          "height": 40,
        } },
        { selector: 'node[truth = "declared"]', style: { "border-color": color("--accent", "#3e63b4"), "border-width": 3 } },
        { selector: 'node[truth = "runtime"]', style: { "border-color": color("--success", "#277553"), "border-width": 3 } },
        { selector: 'node[truth = "inferred"]', style: { "border-color": color("--warn", "#8a5a00"), "border-style": "dashed" } },
        { selector: 'node[kind = "external"]', style: { "shape": "ellipse" } },
        { selector: 'node[kind = "entrypoint"]', style: { "shape": "diamond", "width": 82, "height": 58 } },
        { selector: "edge", style: {
          "curve-style": "bezier",
          "line-color": color("--border-strong", "#687080"),
          "target-arrow-color": color("--border-strong", "#687080"),
          "target-arrow-shape": "triangle",
          "arrow-scale": 0.75,
          "width": 1.2,
        } },
        { selector: 'edge[truth = "runtime"]', style: { "line-color": color("--success", "#277553"), "target-arrow-color": color("--success", "#277553"), "width": 2.5 } },
        { selector: 'edge[truth = "inferred"]', style: { "line-style": "dashed", "line-color": color("--warn", "#8a5a00"), "target-arrow-color": color("--warn", "#8a5a00") } },
        { selector: ":selected", style: { "overlay-opacity": 0, "border-color": color("--accent-strong", "#5b87e0"), "border-width": 4 } },
      ],
    });

    function sourceCoordinate(item) {
      var evidence = item.evidence || [];
      if (!evidence.length && item.path) evidence = [{ path: item.path, line: item.line || 1 }];
      return evidence;
    }

    function showDetail(item, type) {
      detail.textContent = "";
      detail.appendChild(node("h3", "map-detail-title", type === "edge" ? item.kind.replace(/_/g, " ") : item.label));
      var meta = node("p", "map-detail-meta");
      var truth = node("span", "map-truth", item.truth);
      truth.dataset.truth = item.truth;
      meta.appendChild(truth);
      meta.appendChild(document.createTextNode(type === "edge" ? item.confidence + " confidence" : item.kind));
      detail.appendChild(meta);
      if (type === "edge") detail.appendChild(node("p", "", item.reason));
      else if ((item.attributes || {}).qualified_name) detail.appendChild(node("p", "", item.attributes.qualified_name));
      var evidence = sourceCoordinate(item);
      detail.appendChild(node("h4", "", evidence.length ? "Evidence" : "Evidence unavailable"));
      var list = node("ul", "map-evidence");
      evidence.forEach(function (coordinate) {
        var row = node("li", "map-coordinate");
        var label = coordinate.path + ":" + coordinate.line;
        if (graph.snapshot.source_base) {
          var link = node("a", "", label);
          link.href = graph.snapshot.source_base + coordinate.path + "#L" + coordinate.line;
          link.target = "_blank";
          link.rel = "noopener";
          row.appendChild(link);
        } else row.textContent = label;
        if (coordinate.note) row.appendChild(document.createTextNode(" — " + coordinate.note));
        list.appendChild(row);
      });
      detail.appendChild(list);
      if (graph.snapshot.dirty) detail.appendChild(node("p", "", "Dirty snapshot: source links are withheld because the recorded commit may not contain these local coordinates."));
    }

    function renderTable() {
      table.textContent = "";
      var head = node("thead");
      var headRow = node("tr");
      ["Node", "Kind", "Truth", "Source"].forEach(function (label) { headRow.appendChild(node("th", "", label)); });
      head.appendChild(headRow);
      table.appendChild(head);
      var body = node("tbody");
      current.nodes.forEach(function (item) {
        var row = node("tr");
        var nameCell = node("td");
        var button = node("button", "map-button", item.label);
        button.type = "button";
        button.addEventListener("click", function () {
          cy.getElementById(item.id).select();
          showDetail(item, "node");
        });
        nameCell.appendChild(button);
        row.appendChild(nameCell);
        row.appendChild(node("td", "", item.kind));
        row.appendChild(node("td", "", item.truth));
        row.appendChild(node("td", "map-coordinate", item.path ? item.path + ":" + (item.line || 1) : "—"));
        body.appendChild(row);
      });
      table.appendChild(body);
    }

    function writeUrl() {
      if (!global.history) return;
      var params = new URLSearchParams(global.location.search);
      ["map-view", "map-focus", "map-direction", "map-depth", "map-layer"].forEach(function (key) { params.delete(key); });
      params.set("map-view", state.view);
      if (state.focus) params.set("map-focus", state.focus);
      params.set("map-direction", state.direction);
      params.set("map-depth", String(state.depth));
      TRUTHS.forEach(function (truth) { if (state.layers[truth]) params.append("map-layer", truth); });
      var query = params.toString();
      global.history.replaceState(null, "", global.location.pathname + (query ? "?" + query : "") + global.location.hash);
    }

    function readUrl() {
      var params = new URLSearchParams(global.location.search);
      var wantedView = params.get("map-view");
      if (wantedView && graph.views.some(function (view) { return view.id === wantedView; })) state.view = wantedView;
      var wantedFocus = resolve(graph, params.get("map-focus") || "");
      if (wantedFocus) state.focus = wantedFocus.id;
      var wantedDirection = params.get("map-direction");
      if (["both", "incoming", "outgoing"].indexOf(wantedDirection) !== -1) state.direction = wantedDirection;
      if (params.has("map-depth")) {
        var wantedDepth = Number(params.get("map-depth"));
        if (wantedDepth >= 0 && wantedDepth <= 5) state.depth = wantedDepth;
      }
      var wantedLayers = params.getAll("map-layer");
      if (wantedLayers.length) {
        state.layers = {};
        wantedLayers.forEach(function (truth) { if (TRUTHS.indexOf(truth) !== -1) state.layers[truth] = true; });
      }
    }

    function render() {
      current = project(graph, state, indexes, forced);
      cy.elements().remove();
      cy.add(current.nodes.map(function (item) {
        var data = { id: item.id, label: item.label, kind: item.kind, truth: item.truth };
        return { group: "nodes", data: data };
      }).concat(current.edges.map(function (edge) {
        return { group: "edges", data: { id: edge.id, source: edge.source, target: edge.target, kind: edge.kind, truth: edge.truth } };
      })));
      if (current.nodes.length) {
        var roots = current.nodes.filter(function (item) { return item.kind === "entrypoint"; }).map(function (item) { return "#" + CSS.escape(item.id); });
        cy.layout({ name: "breadthfirst", directed: true, padding: 36, spacingFactor: 1.25, roots: roots.join(",") || undefined, animate: false }).run();
        cy.fit(undefined, 32);
      }
      var coverage = graph.snapshot.coverage || {};
      var unsupported = (coverage.unsupported_languages || []).map(function (row) {
        return row.files + " " + row.language;
      }).join(", ");
      status.textContent = current.nodes.length + " nodes · " + current.edges.length + " relationships · " +
        (coverage.parsed_files || 0) + "/" + (coverage.candidate_files || 0) + " Python files parsed" +
        ((coverage.parse_failures || []).length ? " · " + coverage.parse_failures.length + " parse failures" : "") +
        (unsupported ? " · unsupported: " + unsupported : "") +
        (graph.snapshot.dirty ? " · dirty snapshot" : "");
      canvas.setAttribute("aria-label", status.textContent + "; use the table below for keyboard navigation");
      renderTable();
      detail.textContent = "";
      detail.appendChild(node("h3", "map-detail-title", current.view.question || "Select a node or relationship"));
      detail.appendChild(node("p", "", "Select any node or edge to inspect why it exists and where its evidence lives."));
      if (!current.nodes.length) detail.appendChild(node("p", "map-empty", "No nodes remain in the selected truth layers."));
      writeUrl();
    }

    function syncControls() {
      viewSelect.value = state.view;
      focusInput.value = state.focus;
      directionSelect.value = state.direction;
      depthSelect.value = String(state.depth);
      TRUTHS.forEach(function (truth) { layerInputs[truth].checked = !!state.layers[truth]; });
    }

    function shortestPath(from, to) {
      var allowed = {};
      TRUTHS.forEach(function (truth) { if (state.layers[truth]) allowed[truth] = true; });
      var queue = [from.id];
      var seen = {};
      var previous = {};
      seen[from.id] = true;
      while (queue.length) {
        var currentId = queue.shift();
        if (currentId === to.id) break;
        indexes.outgoing[currentId].filter(function (edge) { return allowed[edge.truth]; }).forEach(function (edge) {
          if (!seen[edge.target]) {
            seen[edge.target] = true;
            previous[edge.target] = currentId;
            queue.push(edge.target);
          }
        });
      }
      if (!seen[to.id]) return null;
      var result = [to.id];
      while (result[result.length - 1] !== from.id) result.push(previous[result[result.length - 1]]);
      return result.reverse();
    }

    cy.on("tap", "node", function (event) { showDetail(indexes.nodes[event.target.id()], "node"); });
    cy.on("tap", "edge", function (event) {
      var id = event.target.id();
      var edge = graph.edges.filter(function (item) { return item.id === id; })[0];
      showDetail(edge, "edge");
    });
    viewSelect.addEventListener("change", function () {
      state.view = viewSelect.value;
      var next = definition(graph, state.view);
      state.direction = next.direction || state.direction;
      state.depth = next.depth == null ? state.depth : next.depth;
      state.layers = {};
      (next.layers || TRUTHS).forEach(function (truth) { state.layers[truth] = true; });
      state.focus = "";
      forced = null;
      syncControls();
      render();
    });
    focusInput.addEventListener("change", function () {
      var item = resolve(graph, focusInput.value);
      if (!item) { status.textContent = "Focus is ambiguous or unknown; choose a stable id from the list."; return; }
      state.focus = item.id;
      forced = null;
      focusInput.value = item.id;
      render();
      showDetail(item, "node");
    });
    directionSelect.addEventListener("change", function () { state.direction = directionSelect.value; forced = null; render(); });
    depthSelect.addEventListener("change", function () { state.depth = Number(depthSelect.value); forced = null; render(); });
    TRUTHS.forEach(function (truth) {
      layerInputs[truth].addEventListener("change", function () {
        state.layers[truth] = layerInputs[truth].checked;
        forced = null;
        render();
      });
    });
    pathButton.addEventListener("click", function () {
      var from = resolve(graph, pathFrom.value);
      var to = resolve(graph, pathTo.value);
      if (!from || !to) { status.textContent = "Both path endpoints must resolve to one stable node id."; return; }
      forced = shortestPath(from, to);
      if (!forced) { status.textContent = "No directed path exists in the selected truth layers."; return; }
      state.focus = "";
      focusInput.value = "";
      render();
      status.textContent += " · directed path " + from.label + " → " + to.label;
    });
    resetButton.addEventListener("click", function () {
      var reset = definition(graph, options.view || "overview");
      state.view = reset.id;
      state.focus = "";
      state.direction = reset.direction || "both";
      state.depth = reset.depth == null ? 2 : reset.depth;
      state.layers = {};
      (reset.layers || TRUTHS).forEach(function (truth) { state.layers[truth] = true; });
      forced = null;
      pathFrom.value = pathTo.value = "";
      syncControls();
      render();
    });
    jsonButton.addEventListener("click", function () { download("codegraph-view.json", JSON.stringify(current, null, 2) + "\n", "application/json"); });
    mermaidButton.addEventListener("click", function () { download("codegraph-view.mmd", mermaid(current)); });
    svgButton.addEventListener("click", function () { download("codegraph-view.svg", svg(current, cy), "image/svg+xml"); });

    readUrl();
    syncControls();
    render();
    return {
      data: function () { return clone(current); },
      focus: function (reference) {
        var item = resolve(graph, reference);
        if (!item) throw new Error("ArtooMap focus must resolve to one node");
        state.focus = item.id;
        forced = null;
        syncControls();
        render();
      },
      reset: function () { resetButton.click(); },
    };
  }

  global.ArtooMap = { create: create, mermaid: mermaid };
})(typeof window !== "undefined" ? window : this);
