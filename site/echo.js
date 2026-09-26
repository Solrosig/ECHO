/* ECHO listening test: trial state, seeded order, affect grid, recovery.
   Plain JS, no framework, no CDN. The whole instrument is this file plus test.html. */

(function (global) {
  "use strict";

  var KEY = "echo-listening-v1";

  /* --- seeded order ---------------------------------------------------
     The participant code is the seed, so the order can be rebuilt from the responses file
     alone, with no separate seed to record or lose. An unseeded order could not be
     reconstructed, leaving order effects untestable rather than merely unknown. */

  function seedFrom(code) {
    var h = 2166136261 >>> 0;
    for (var i = 0; i < code.length; i++) {
      h ^= code.charCodeAt(i);
      h = Math.imul(h, 16777619) >>> 0;
    }
    return h >>> 0;
  }

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function shuffled(items, code) {
    var rnd = mulberry32(seedFrom(code));
    var a = items.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(rnd() * (i + 1));
      var t = a[i]; a[i] = a[j]; a[j] = t;
    }
    return a;
  }

  /* --- persistence ----------------------------------------------------
     localStorage after every trial. Static hosting has no server-side session, and at n = 5 a
     browser crash at trial 47 costing a whole session is 20 % of the study. */

  function load() {
    try { return JSON.parse(global.localStorage.getItem(KEY) || "null"); }
    catch (e) { return null; }
  }

  function save(state) {
    try { global.localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* private mode */ }
  }

  function clear() {
    try { global.localStorage.removeItem(KEY); } catch (e) { /* ignore */ }
  }

  /* --- the affect grid ------------------------------------------------
     One click reports both dimensions. The format follows the EmojiGrid (Toet & van Erp),
     validated for affective appraisal (audio included). ECHO adapts it from self-report of felt
     affect to judgement of perceived expressed affect and declares the adaptation, hence the page's
     instruction "Judge the speaker's emotion, not how the recording made you feel".

     The quadrant is derived from the click, not chosen from four buttons: the project's own
     Layer-3 data showed kappa = -0.017 where Spearman rho = +0.620 on the same comparison, so
     discretising destroyed the signal. Coordinates keep both analyses available. */

  function quadrantOf(v, a) {
    if (a >= 0) { return v >= 0 ? "Q1" : "Q2"; }
    return v >= 0 ? "Q4" : "Q3";
  }

  function attachGrid(svg, onPick) {
    var SZ = 260, PAD = 18, span = SZ - 2 * PAD;
    function toValues(evt) {
      var r = svg.getBoundingClientRect();
      var px = ((evt.clientX - r.left) / r.width) * SZ;
      var py = ((evt.clientY - r.top) / r.height) * SZ;
      var v = ((px - PAD) / span) * 2 - 1;
      var a = 1 - ((py - PAD) / span) * 2;
      return [Math.max(-1, Math.min(1, v)), Math.max(-1, Math.min(1, a))];
    }
    function place(evt) {
      var va = toValues(evt);
      onPick(Math.round(va[0] * 100) / 100, Math.round(va[1] * 100) / 100);
    }
    svg.addEventListener("click", place);
    svg.addEventListener("keydown", function (e) {
      // Keyboard input: a mouse-only test would exclude participants for no methodological reason.
      var map = { Q1: [0.6, 0.6], Q2: [-0.6, 0.6], Q3: [-0.6, -0.6], Q4: [0.6, -0.6] };
      var k = { 1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4" }[e.key];
      if (k) { e.preventDefault(); onPick(map[k][0], map[k][1]); }
    });
  }

  function drawDot(svg, v, a) {
    var SZ = 260, PAD = 18, span = SZ - 2 * PAD;
    var cx = PAD + ((v + 1) / 2) * span;
    var cy = PAD + ((1 - a) / 2) * span;
    var dot = svg.querySelector(".dot"), halo = svg.querySelector(".halo");
    dot.setAttribute("cx", cx); dot.setAttribute("cy", cy); dot.setAttribute("r", 7);
    halo.setAttribute("cx", cx); halo.setAttribute("cy", cy); halo.setAttribute("r", 13);
  }

  global.ECHO = {
    KEY: KEY,
    seedFrom: seedFrom,
    shuffled: shuffled,
    quadrantOf: quadrantOf,
    attachGrid: attachGrid,
    drawDot: drawDot,
    load: load,
    save: save,
    clear: clear
  };
})(window);
