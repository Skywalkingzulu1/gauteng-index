/* Gauteng Index client-side search. Progressive enhancement only: the
   form submits to /search/?q= and every listing is a plain link, so the
   page works with scripting off. With scripting on, results filter live
   from assets/search-index.json (all Gauteng businesses, ~2 MB). */
(function () {
  "use strict";
  var INDEX_URL = "ASSET_BASE" + "search-index.json";
  var MAX_RESULTS = 60;
  var index = null;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fold(s) {
    return String(s == null ? "" : s).toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  function score(e, q) {
    var n = fold(e.n), k = fold(e.k || ""), c = fold(e.c || ""),
        z = fold(e.z || "");
    if (n === q) return 0;
    if (n.indexOf(q) === 0) return 1;
    if (n.indexOf(q) !== -1) return 2;
    if (k.indexOf(q) !== -1) return 3;
    if (c.indexOf(q) !== -1) return 4;
    if (z.indexOf(q) !== -1) return 5;
    return -1;
  }

  function highlight(name, q) {
    var i = fold(name).indexOf(q);
    if (i === -1 || !q) return esc(name);
    return esc(name.slice(0, i)) + "<mark>" +
      esc(name.slice(i, i + q.length)) + "</mark>" +
      esc(name.slice(i + q.length));
  }

  function render(q, box, status) {
    if (!q) {
      box.innerHTML = "<p class='search-empty'>Type a business name, " +
        "category or suburb above.</p>";
      if (status) status.textContent = "";
      return;
    }
    var out = [];
    for (var i = 0; i < index.length; i++) {
      var s = score(index[i], q);
      if (s !== -1) out.push({ e: index[i], s: s });
    }
    out.sort(function (a, b) {
      return a.s - b.s || (a.e.n < b.e.n ? -1 : 1);
    });
    out = out.slice(0, MAX_RESULTS);
    if (!out.length) {
      box.innerHTML = "<p class='search-empty'>Nothing in the Gauteng " +
        "index matches. Try a shorter word, or browse by category.</p>";
      if (status) status.textContent = "0 results";
      return;
    }
    box.innerHTML = out.map(function (r) {
      var e = r.e;
      return "<a class='result' href='" + esc(e.u) + "'>" +
        "<span class='result-name'>" + highlight(e.n, q) + "</span>" +
        "<span class='result-meta'>" + esc(e.c) + " &middot; " +
        esc(e.z) + "</span></a>";
    }).join("");
    if (status) status.textContent =
      out.length + (out.length === 1 ? " result" : " results");
  }

  function boot() {
    var form = document.querySelector(".si-search-form");
    if (!form) return;
    var input = form.querySelector("input[name='q']");
    var box = document.querySelector(".si-search-results");
    var status = document.querySelector(".si-search-status");
    if (!input || !box) return;
    var params = new URLSearchParams(window.location.search);
    var start = (params.get("q") || "").trim();
    function current() { render(fold(input.value.trim()), box, status); }
    fetch(INDEX_URL, { mode: "same-origin" }).then(function (r) {
      if (!r.ok) throw new Error("http " + r.status);
      return r.json();
    }).then(function (d) {
      index = d;
      if (start) { input.value = start; current(); }
    }).catch(function () {
      box.innerHTML = "<p class='search-empty'>The search index could " +
        "not be loaded. Browse by category instead.</p>";
    });
    var deb = null;
    input.addEventListener("input", function () {
      clearTimeout(deb);
      deb = setTimeout(current, 250);
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      current();
      try {
        var u = new URL(window.location.href);
        u.searchParams.set("q", input.value.trim());
        window.history.replaceState(null, "", u.toString());
      } catch (err) { /* shareable URL is a nicety, not a need */ }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
