// In-page checks for `artoo verify --browser` and `artoo build`.
//
// Evaluated by Playwright as one async function after a page loads. It
// returns plain data; verify.py turns it into messages. Every check here is
// tuned to stay quiet on sound pages: a check that cries wolf gets ignored on
// the day it is right, so each one skips the cases it cannot judge.
async () => {
  const LIMIT = 40;
  const SMALL = 10.5; // px; see the small-text check
  const root = document.documentElement;
  const body = document.body;
  const out = {
    overflow: null, image: [], diagram: [], clipped: [], small: [], contrast: [], overlap: [],
    counts: {},
  };
  if (!body) return out;

  // ---- where a finding lives -------------------------------------------------

  const headings = Array.from(
    document.querySelectorAll("h1[id], h2[id], h3[id], h4[id], h5[id], h6[id]")
  );

  function headingFor(el) {
    // Headings are in document order, so the last one at or before `el` is
    // the section a reader would scroll to.
    let lo = 0, hi = headings.length - 1, found = "";
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const h = headings[mid];
      const before = h === el || h.contains(el) ||
        (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
      if (before) { found = h.id; lo = mid + 1; } else { hi = mid - 1; }
    }
    return found;
  }

  function segment(el) {
    if (el.id && /^[A-Za-z][\w-]*$/.test(el.id)) return "#" + el.id;
    const tag = el.tagName.toLowerCase();
    const classes = Array.from(el.classList)
      .filter((c) => /^[A-Za-z_][\w-]*$/.test(c) && !/^(is|has|js)-/.test(c))
      .slice(0, 2);
    let s = tag + classes.map((c) => "." + c).join("");
    const parent = el.parentElement;
    if (parent) {
      const same = Array.from(parent.children).filter((c) => c.tagName === el.tagName);
      if (same.length > 1 && same.filter((c) => c.matches(s)).length > 1) {
        s += ":nth-of-type(" + (same.indexOf(el) + 1) + ")";
      }
    }
    return s;
  }

  function selector(el) {
    const parts = [];
    let node = el;
    while (node && node !== body && node !== root && parts.length < 4) {
      const s = segment(node);
      parts.unshift(s);
      if (s.startsWith("#")) break;
      node = node.parentElement;
    }
    return parts.join(" > ") || el.tagName.toLowerCase();
  }

  function where(el, extra) {
    const src = el.closest("[data-src]");
    return Object.assign(
      { sel: selector(el), heading: headingFor(el), src: src ? src.getAttribute("data-src") : "" },
      extra || {}
    );
  }

  function push(rule, item) {
    out.counts[rule] = (out.counts[rule] || 0) + 1;
    if (out[rule].length < LIMIT) out[rule].push(item);
  }

  function snippet(text) {
    const t = text.replace(/\s+/g, " ").trim();
    return t.length > 40 ? t.slice(0, 39) + "…" : t;
  }

  // ---- diagrams: give the renderer a moment, then look ------------------------

  const DIAGRAM = "pre.mermaid, pre > code.language-mermaid, .mermaid, [data-diagram]";
  function diagramBlocks() {
    const seen = new Set();
    for (const node of document.querySelectorAll(DIAGRAM)) {
      const block = node.tagName === "CODE" ? node.parentElement : node;
      // A wrapper and the block inside it are one diagram: keep the outermost.
      if (block.parentElement && block.parentElement.closest(DIAGRAM)) continue;
      seen.add(block);
    }
    return Array.from(seen);
  }
  function unrendered() {
    // An onError diagram already logged a console error naming it; counting
    // it here too would report one fault twice.
    return diagramBlocks().filter(
      (b) => !b.querySelector("svg") && b.getAttribute("data-diagram") !== "error"
    );
  }
  for (let waited = 0; waited < 4000 && unrendered().length; waited += 100) {
    await new Promise((r) => setTimeout(r, 100));
  }
  if (document.fonts && document.fonts.ready) await document.fonts.ready;
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  for (const block of unrendered()) {
    push("diagram", where(block, { text: snippet(block.textContent || "") }));
  }

  // ---- broken images ----------------------------------------------------------

  const suspects = Array.from(document.images).filter(
    (img) => img.complete && img.naturalWidth === 0 && (img.currentSrc || img.getAttribute("src"))
  );
  // An SVG without intrinsic size can report naturalWidth 0 and still draw;
  // decode() is the browser's own verdict on whether the bytes are an image.
  const broken = await Promise.all(
    suspects.map((img) => img.decode().then(() => false, () => true))
  );
  suspects.forEach((img, i) => {
    if (broken[i]) push("image", where(img, { detail: img.getAttribute("src") || img.currentSrc }));
  });

  // ---- shared helpers ---------------------------------------------------------

  const style = new Map();
  const cs = (el) => {
    let s = style.get(el);
    if (!s) { s = getComputedStyle(el); style.set(el, s); }
    return s;
  };
  const SKIP_TAGS = new Set([
    "SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "HEAD", "TITLE", "META", "LINK", "OPTION",
  ]);
  const FIELDS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

  function visuallyHidden(el) {
    // The sr-only family: a 1px box, clip, or clip-path that hides text from
    // sight while keeping it for assistive tech. Deliberate, never a defect.
    for (let n = el; n && n !== root; n = n.parentElement) {
      const s = cs(n);
      if (s.clip && s.clip !== "auto") return true;
      if (s.clipPath && /inset\(\s*50%/.test(s.clipPath)) return true;
      const r = n.getBoundingClientRect();
      if ((r.width <= 1 || r.height <= 1) && (s.overflow !== "visible" || s.position === "absolute")) {
        return true;
      }
    }
    return false;
  }

  function visible(el) {
    if (el.checkVisibility) {
      if (!el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return false;
    }
    return el.getClientRects().length > 0;
  }

  function ownTextNodes(el) {
    return Array.from(el.childNodes).filter(
      (n) => n.nodeType === Node.TEXT_NODE && n.nodeValue.trim()
    );
  }

  const range = document.createRange();
  function textRects(nodes) {
    const rects = [];
    for (const node of nodes) {
      range.selectNodeContents(node);
      for (const r of range.getClientRects()) if (r.width > 0 && r.height > 0) rects.push(r);
    }
    return rects;
  }

  // Every visible element that carries text of its own, measured once.
  const texts = [];
  for (const el of body.querySelectorAll("*")) {
    if (SKIP_TAGS.has(el.tagName) || FIELDS.has(el.tagName)) continue;
    // Diagram text is drawn by the renderer, and a failed diagram's error box
    // is already reported through the console.
    if (el.closest("svg, math, [data-diagram]")) continue;
    const nodes = ownTextNodes(el);
    if (!nodes.length || !visible(el)) continue;
    const text = nodes.map((n) => n.nodeValue).join(" ");
    // A lone "·" or "→" is a separator or ornament, not something to read.
    if (!/[\p{L}\p{N}]/u.test(text)) continue;
    const rects = textRects(nodes);
    if (!rects.length) continue;
    texts.push({ el, nodes, rects, text });
  }
  const hiddenCache = new Map();
  const isHidden = (el) => {
    if (!hiddenCache.has(el)) hiddenCache.set(el, visuallyHidden(el));
    return hiddenCache.get(el);
  };

  // ---- horizontal overflow: name the boxes that cause it ----------------------

  const vw = root.clientWidth;
  if (root.scrollWidth > vw + 1) {
    const clipsX = (s) => s.overflowX !== "visible";
    const offenders = [];
    const offenderSet = new Set();
    for (const el of body.querySelectorAll("*")) {
      if (SKIP_TAGS.has(el.tagName)) continue;
      const r = el.getBoundingClientRect();
      if (!r.width) continue;
      // A long unbroken word spills out of a box that is itself narrow
      // enough, so the box's own text has to be measured too.
      let right = r.right;
      if (right <= vw + 1) {
        for (const t of textRects(ownTextNodes(el))) right = Math.max(right, t.right);
      }
      right += window.scrollX;
      if (right <= vw + 1) continue;
      let contained = false;
      for (let n = el; n && n !== body; n = n.parentElement) {
        const s = cs(n);
        // Fixed boxes never widen the page; a scroll or clip container
        // already keeps its children from doing so.
        if (s.position === "fixed" || (n !== el && clipsX(s))) { contained = true; break; }
      }
      if (contained) continue;
      offenderSet.add(el);
      offenders.push({ el, right });
    }
    // Report root causes: an offender inside another offender is its symptom.
    const roots = offenders.filter(({ el }) => {
      for (let n = el.parentElement; n && n !== body; n = n.parentElement) {
        if (offenderSet.has(n)) return false;
      }
      return true;
    });
    roots.sort((a, b) => b.right - a.right);
    out.overflow = {
      width: root.scrollWidth,
      viewport: vw,
      total: roots.length,
      offenders: roots.slice(0, 3).map(({ el, right }) => where(el, { right: Math.round(right) })),
    };
  }

  // ---- clipped text -----------------------------------------------------------

  const clipsAny = (s) => s.overflowX !== "visible" || s.overflowY !== "visible";
  const scrolls = (v) => v === "auto" || v === "scroll";
  for (const el of body.querySelectorAll("*")) {
    if (SKIP_TAGS.has(el.tagName) || FIELDS.has(el.tagName)) continue;
    const s = cs(el);
    if (!clipsAny(s)) continue;
    // A scroll container shows its overflow on demand; ellipsis and
    // line-clamp are truncation the author chose and the reader can see.
    if (scrolls(s.overflowX) || scrolls(s.overflowY)) continue;
    if (s.textOverflow === "ellipsis" || (s.webkitLineClamp && s.webkitLineClamp !== "none")) {
      continue;
    }
    if (el.scrollWidth <= el.clientWidth + 1 && el.scrollHeight <= el.clientHeight + 1) continue;
    if (!visible(el) || isHidden(el)) continue;
    const box = el.getBoundingClientRect();
    const inner = {
      left: box.left + el.clientLeft,
      top: box.top + el.clientTop,
      right: box.left + el.clientLeft + el.clientWidth,
      bottom: box.top + el.clientTop + el.clientHeight,
    };
    let hit = null;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node && !hit; node = walker.nextNode()) {
      if (!node.nodeValue.trim()) continue;
      const parent = node.parentElement;
      // Text belongs to its nearest clipping box; a nested clipper is judged
      // on its own turn.
      let owner = parent;
      while (owner && owner !== el && !clipsAny(cs(owner))) owner = owner.parentElement;
      if (owner !== el || !visible(parent)) continue;
      const rects = textRects([node]);
      if (!rects.length) continue;
      const u = {
        left: Math.min(...rects.map((r) => r.left)),
        top: Math.min(...rects.map((r) => r.top)),
        right: Math.max(...rects.map((r) => r.right)),
        bottom: Math.max(...rects.map((r) => r.bottom)),
      };
      // Text wholly outside its box is staged off-screen on purpose (a
      // carousel, an inactive slide); text cut at the edge is the defect.
      const shows = u.right > inner.left && u.left < inner.right &&
        u.bottom > inner.top && u.top < inner.bottom;
      const spills = u.right > inner.right + 2 || u.bottom > inner.bottom + 2 ||
        u.left < inner.left - 2 || u.top < inner.top - 2;
      if (shows && spills) hit = node;
    }
    if (hit) push("clipped", where(el, { text: snippet(hit.nodeValue) }));
  }

  // ---- small text -------------------------------------------------------------

  for (const t of texts) {
    if (isHidden(t.el)) continue;
    const size = parseFloat(cs(t.el).fontSize);
    // Calibrated on real artifacts: 11px uppercase labels and 0.9em code in a
    // 12px colophon (10.8px) are deliberate and legible, and flagging them
    // buried the 8-10px text that is not. So the line sits at 10.5px.
    if (size < SMALL) {
      push("small", where(t.el, { size: Math.round(size * 10) / 10, text: snippet(t.text) }));
    }
  }

  // ---- contrast ---------------------------------------------------------------

  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const colors = new Map();
  function rgba(value) {
    // The canvas resolves every CSS colour syntax (oklch, color-mix, named)
    // to sRGB, which is what contrast is defined over.
    if (colors.has(value)) return colors.get(value);
    let c = null;
    if (value && value !== "transparent") {
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = "#000";
      ctx.fillStyle = value;
      ctx.fillRect(0, 0, 1, 1);
      const d = ctx.getImageData(0, 0, 1, 1).data;
      c = [d[0], d[1], d[2], d[3] / 255];
    } else {
      c = [0, 0, 0, 0];
    }
    colors.set(value, c);
    return c;
  }
  const over = (top, under) => {
    const a = top[3];
    return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a)).concat(1);
  };
  const lum = (c) => {
    const ch = c.slice(0, 3).map((v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  };
  const hex = (c) => "#" + c.slice(0, 3).map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");

  function background(el) {
    // Walk outward compositing translucent backgrounds until one is opaque.
    // Anything the walk cannot see through (an image, a gradient, a blend,
    // a box positioned over unrelated content) makes the answer unknown,
    // and an unknown is skipped rather than guessed.
    const layers = [];
    let opacity = 1;
    for (let n = el; n; n = n.parentElement) {
      const s = cs(n);
      if (s.backgroundImage !== "none") return null;
      if (s.mixBlendMode !== "normal" || (s.filter && s.filter !== "none")) return null;
      if (s.backdropFilter && s.backdropFilter !== "none") return null;
      const bg = rgba(s.backgroundColor);
      if (bg[3] > 0) layers.push(bg);
      if (bg[3] >= 1) break;
      // A faded box fades its text against whatever shows through it.
      opacity *= parseFloat(s.opacity);
      if (s.position === "absolute" || s.position === "fixed") return null;
    }
    const base = layers.length && layers[layers.length - 1][3] >= 1 ? [] : [[255, 255, 255, 1]];
    const color = base.concat(layers.reverse()).reduce((acc, l) => over(l, acc));
    return { color, opacity };
  }

  for (const t of texts) {
    if (isHidden(t.el)) continue;
    if (t.el.closest(":disabled, [aria-disabled='true'], [inert]")) continue;
    const s = cs(t.el);
    const fill = s.webkitTextFillColor || s.color;
    let fg = rgba(fill);
    if (fg[3] === 0) continue;
    if (s.textShadow && s.textShadow !== "none") continue;
    const bg = background(t.el);
    if (!bg) continue;
    fg = over([fg[0], fg[1], fg[2], fg[3] * bg.opacity], bg.color);
    const l1 = lum(fg), l2 = lum(bg.color);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const size = parseFloat(s.fontSize);
    const large = size >= 24 || (size >= 18.66 && parseInt(s.fontWeight, 10) >= 700);
    const need = large ? 3 : 4.5;
    if (Math.round(ratio * 100) / 100 < need) {
      push("contrast", where(t.el, {
        ratio: Math.round(ratio * 100) / 100, need, fg: hex(fg), bg: hex(bg.color),
        text: snippet(t.text),
      }));
    }
  }

  // ---- positioned text over other text ----------------------------------------

  // Fixed chrome (a toolbar, a drawer) floats over content by design, and
  // what it covers depends on where the reader has scrolled; only text set
  // inside the flow with `position: absolute` can collide by mistake.
  const FIXED = {};
  function positionedRoot(el) {
    let found = null;
    for (let n = el; n && n !== body; n = n.parentElement) {
      const p = cs(n).position;
      if (p === "fixed" || p === "sticky") return FIXED;
      if (p === "absolute" && !found) found = n;
    }
    return found;
  }
  const intersects = (a, b) => {
    const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    // A shared hairline is layout, not collision: demand a real overlap of
    // the glyph boxes in both directions.
    return w > 2 && h > Math.min(a.height, b.height) * 0.4;
  };
  const placed = texts
    .filter((t) => !isHidden(t.el))
    .map((t) => ({ ...t, root: positionedRoot(t.el) }))
    .filter((t) => t.root !== FIXED);
  const reported = new Set();
  for (const a of placed) {
    if (!a.root || reported.has(a.root)) continue;
    for (const b of placed) {
      if (b === a || b.root === a.root) continue;
      if (a.root.contains(b.el) || b.el.contains(a.root)) continue;
      // Two positioned layers that collide are one finding, not two.
      if (b.root && reported.has(b.root)) continue;
      if (!a.rects.some((ra) => b.rects.some((rb) => intersects(ra, rb)))) continue;
      reported.add(a.root);
      push("overlap", where(a.el, {
        text: snippet(a.text), other: selector(b.el), otherText: snippet(b.text),
      }));
      break;
    }
  }

  return out;
}
