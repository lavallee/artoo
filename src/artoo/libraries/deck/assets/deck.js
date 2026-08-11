/* artoo-deck — navigation for presentation artifacts.
 *
 * Progressive enhancement: with JavaScript off, every slide is still in the
 * document and printing still produces the full deck. This file adds the
 * one-slide-at-a-time view, the overview, notes, and keyboard/touch control.
 *
 * It reads structure from the markup rather than from configuration:
 *   .deck-slide[data-act]    groups slides into acts in the overview
 *   .deck-slide[data-short]  labels a slide in the overview
 *   .deck-notes              speaker notes, hidden until toggled
 */
(function () {
  "use strict";

  var stage = document.querySelector("[data-deck]");
  if (!stage) return;

  var slides = Array.prototype.slice.call(stage.querySelectorAll(".deck-slide"));
  if (!slides.length) return;

  var body = document.body;
  var overview = document.querySelector("[data-deck-overview]");
  var bar = document.querySelector("[data-deck-progress]");
  var current = 0;

  function each(selector, fn) {
    Array.prototype.slice.call(document.querySelectorAll(selector)).forEach(fn);
  }

  /* ---- overview grid, grouped by act ---- */

  if (overview) {
    var acts = [];
    slides.forEach(function (slide, i) {
      var act = slide.getAttribute("data-act") || "Slides";
      var group = acts[acts.length - 1];
      if (!group || group.name !== act) {
        group = { name: act, items: [] };
        acts.push(group);
      }
      group.items.push({
        index: i,
        label: slide.getAttribute("data-short") || "Slide " + (i + 1),
      });
    });
    acts.forEach(function (group) {
      var wrap = document.createElement("div");
      wrap.className = "deck-ov-act";
      var heading = document.createElement("h5");
      heading.textContent = group.name;
      wrap.appendChild(heading);
      var grid = document.createElement("div");
      grid.className = "deck-ov-grid";
      group.items.forEach(function (item) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "deck-ov-item";
        button.setAttribute("data-index", String(item.index));
        var n = document.createElement("i");
        n.textContent = String(item.index + 1).padStart(2, "0");
        var label = document.createElement("b");
        label.textContent = item.label;
        button.appendChild(n);
        button.appendChild(label);
        button.addEventListener("click", function () {
          go(item.index);
          toggle("deck-show-overview", false);
        });
        grid.appendChild(button);
      });
      wrap.appendChild(grid);
      overview.appendChild(wrap);
    });
  }

  /* ---- navigation ---- */

  function go(index) {
    index = Math.max(0, Math.min(slides.length - 1, index));
    current = index;
    slides.forEach(function (slide, i) {
      if (i === index) slide.setAttribute("data-active", "");
      else slide.removeAttribute("data-active");
      slide.setAttribute("aria-hidden", i === index ? "false" : "true");
    });
    each("[data-deck-counter]", function (el) {
      el.textContent = index + 1 + " / " + slides.length;
    });
    if (bar) bar.style.width = ((index + 1) / slides.length) * 100 + "%";
    each(".deck-ov-item", function (el) {
      if (Number(el.getAttribute("data-index")) === index) el.setAttribute("data-current", "");
      else el.removeAttribute("data-current");
    });
    if (window.location.hash !== "#" + (index + 1)) {
      history.replaceState(null, "", "#" + (index + 1));
    }
    slides[index].scrollTop = 0;
  }

  function toggle(cls, on) {
    var next = on === undefined ? !body.classList.contains(cls) : on;
    body.classList.toggle(cls, next);
    var map = {
      "deck-show-overview": "[data-deck-toggle=overview]",
      "deck-show-notes": "[data-deck-toggle=notes]",
    };
    if (map[cls]) each(map[cls], function (el) { el.setAttribute("aria-pressed", String(next)); });
  }

  each("[data-deck-prev]", function (el) {
    el.addEventListener("click", function () { go(current - 1); });
  });
  each("[data-deck-next]", function (el) {
    el.addEventListener("click", function () { go(current + 1); });
  });
  each("[data-deck-toggle=overview]", function (el) {
    el.addEventListener("click", function () { toggle("deck-show-overview"); });
  });
  each("[data-deck-toggle=notes]", function (el) {
    el.addEventListener("click", function () { toggle("deck-show-notes"); });
  });
  each("[data-deck-toggle=help]", function (el) {
    el.addEventListener("click", function () { toggle("deck-show-help"); });
  });
  each("[data-deck-help]", function (el) {
    el.addEventListener("click", function () { toggle("deck-show-help", false); });
  });

  document.addEventListener("keydown", function (event) {
    var tag = (event.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || event.target.isContentEditable) return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    var key = event.key;

    if (key === "ArrowRight" || key === "ArrowDown" || key === " " || key === "PageDown") {
      event.preventDefault(); go(current + 1);
    } else if (key === "ArrowLeft" || key === "ArrowUp" || key === "PageUp") {
      event.preventDefault(); go(current - 1);
    } else if (key === "Home") {
      event.preventDefault(); go(0);
    } else if (key === "End") {
      event.preventDefault(); go(slides.length - 1);
    } else if (key >= "1" && key <= "9") {
      go(Number(key) - 1);
    } else if (key === "o" || key === "O") {
      toggle("deck-show-overview");
    } else if (key === "s" || key === "S") {
      toggle("deck-show-notes");
    } else if (key === "f" || key === "F") {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    } else if (key === "p" || key === "P") {
      window.print();
    } else if (key === "?") {
      toggle("deck-show-help");
    } else if (key === "Escape") {
      toggle("deck-show-overview", false);
      toggle("deck-show-notes", false);
      toggle("deck-show-help", false);
    }
  });

  /* ---- touch ---- */

  var touchX = null;
  stage.addEventListener("touchstart", function (event) {
    touchX = event.changedTouches[0].clientX;
  }, { passive: true });
  stage.addEventListener("touchend", function (event) {
    if (touchX === null) return;
    var dx = event.changedTouches[0].clientX - touchX;
    if (Math.abs(dx) > 60) go(current + (dx < 0 ? 1 : -1));
    touchX = null;
  }, { passive: true });

  /* ---- deep links ---- */

  function fromHash() {
    var n = parseInt((window.location.hash || "").replace("#", ""), 10);
    return isNaN(n) ? 0 : n - 1;
  }
  window.addEventListener("hashchange", function () { go(fromHash()); });
  go(fromHash());
})();
