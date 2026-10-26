/* artoo-diagrams: render Mermaid-syntax blocks with the vendored Pele.
   Load pele.global.js and this file as ordinary scripts, in either order;
   rendering waits for the document, so both are present by then. */
(function () {
  "use strict";

  var SELECTOR = "pre.mermaid, pre > code.language-mermaid";

  // A block's id when it has one, otherwise its position, so a console error
  // (which `artoo verify --browser` reports) points at the diagram to fix.
  function where(block, index) {
    return block.id ? "#" + block.id : "diagram " + (index + 1);
  }

  function render(root) {
    var pele = window.pele;
    var scope = root || document;
    var blocks = scope.querySelectorAll(SELECTOR);
    if (!blocks.length) return [];
    if (!pele) {
      console.error(
        "artoo-diagrams: pele.global.js is not loaded; add " +
        '<script src="lib/artoo-diagrams/pele.global.js"></script> to this page'
      );
      return [];
    }
    var mounted = [];
    Array.prototype.forEach.call(blocks, function (node, index) {
      var block = node.tagName === "CODE" ? node.parentElement : node;
      // <pre class="mermaid"><code class="language-mermaid"> matches twice.
      if (!block.isConnected) return;
      var source = node.textContent;
      // A <pre> holding an <svg> inherits pre styling and reads oddly to
      // assistive tech, so the source block is replaced, keeping its id,
      // classes, and data attributes for the author's own CSS and anchors.
      var host = document.createElement("div");
      Array.prototype.forEach.call(block.attributes, function (attr) {
        host.setAttribute(attr.name, attr.value);
      });
      host.classList.add("mermaid");
      host.setAttribute("data-diagram", "rendered");
      block.replaceWith(host);
      mounted.push(pele.mount(host, source, {
        onError: function (error) {
          host.setAttribute("data-diagram", "error");
          var message = error && error.message ? error.message : String(error);
          console.error("artoo-diagrams: " + where(host, index) + ": " + message);
        }
      }));
    });
    return mounted;
  }

  window.ArtooDiagrams = { render: render };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { render(); });
  } else {
    render();
  }
})();
