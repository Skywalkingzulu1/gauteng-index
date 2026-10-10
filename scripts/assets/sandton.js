/* ==========================================================================
   Sandton Index -- site behaviour
   --------------------------------------------------------------------------
   Emitted to site/assets/sandton.js and loaded by every page with defer.

   Three jobs, all progressive enhancement:
     1. mobile nav
     2. in-page card filters (category and suburb pages)
     3. client-side search over /assets/search-index.json

   Nothing here is required to read the site. Every card, every listing and
   every opening hour is server-rendered; JS only hides and reveals.
   ========================================================================== */
(function () {
  "use strict";

  /* -- 1. mobile nav ---------------------------------------------------- */
  function initNav() {
    var btn = document.getElementById("si-nav-toggle");
    var nav = document.getElementById("si-nav");
    if (!btn || !nav) return;

    btn.addEventListener("click", function () {
      var open = nav.className.indexOf("open") > -1;
      nav.className = open ? "site" : "site open";
      btn.setAttribute("aria-expanded", open ? "false" : "true");
      btn.setAttribute("aria-label", open ? "Open menu" : "Close menu");
    });

    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && nav.className.indexOf("open") > -1) {
        nav.className = "site";
        btn.setAttribute("aria-expanded", "false");
        btn.focus();
      }
    });
  }

  /* -- 2. in-page filters ------------------------------------------------ */
  function initFilters() {
    var inputs = document.querySelectorAll(".si-q");
    for (var z = 0; z < inputs.length; z += 1) bindFilter(inputs[z]);
  }

  function bindFilter(input) {
    var sel = input.getAttribute("data-target");
    var root = sel ? document.getElementById(sel) : document;
    if (!root) return;

    var cards = root.querySelectorAll(".card");
    if (!cards.length) return;

    var grids = root.querySelectorAll(".grid");
    var box = input.parentNode;
    var cnt = box.querySelector(".si-count");
    var hint = box.querySelector(".si-none");

    var run = function () {
      var s = input.value.trim().toLowerCase();
      var shown = 0;

      for (var i = 0; i < cards.length; i += 1) {
        var hit = s === "" || cards[i].textContent.toLowerCase().indexOf(s) > -1;
        cards[i].style.display = hit ? "" : "none";
        if (hit) shown += 1;
      }

      if (cnt) cnt.textContent = shown + " of " + cards.length + " shown";
      if (hint) hint.hidden = shown !== 0;

      for (var g = 0; g < grids.length; g += 1) {
        var kids = grids[g].querySelectorAll(".card");
        var any = false;
        for (var k = 0; k < kids.length; k += 1) {
          if (kids[k].style.display !== "none") any = true;
        }
        grids[g].hidden = !any;
        var head = grids[g].previousElementSibling;
        if (head && head.tagName === "H2") head.hidden = !any;
      }
    };

    input.addEventListener("input", run);
    run();
  }

  /* -- 3. search --------------------------------------------------------- */
  function initSearch() {
    var form = document.getElementById("si-search-form");
    if (!form) return;

    var input = document.getElementById("si-search-input");
    var out = document.getElementById("si-search-results");
    var status = document.getElementById("si-search-status");
    var hints = document.getElementById("si-search-hints");
    var index = null;
    var loading = false;

    function say(msg) {
      if (status) status.textContent = msg;
    }

    function esc(s) {
      return String(s).replace(/[&<>"]/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
      });
    }

    /* Wrap the matched run so a result reads as a highlighted match rather
       than as a plain string. The index is build-generated, but it is still
       escaped first -- nothing from search-index.json is trusted as markup. */
    function mark(name, q) {
      var safe = esc(name);
      if (!q) return safe;
      var needle = esc(q).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return safe.replace(new RegExp("(" + needle + ")", "ig"), "<mark>$1</mark>");
    }

/* Rank order, strongest first: exact name, name prefix, name substring,
       the specific OSM type, the broad category, then the suburb. A business
       called "Woolworths" must outrank every shop in the Rivonia suburb. */
    /* When a query returns nothing, the useful answer is a route onwards, not
       a scolding. A near-miss heuristic catches "bakery" when only "Baker"
       is indexed; where nothing is close, offer the largest sections with
       real links so the visitor is never left at a dead end. Category urls
       come from the hub slug already carried on each index entry. */
    var catInfo = null;

    function catalogue() {
      if (!catInfo) {
        catInfo = {};
        for (var i = 0; i < index.length; i += 1) {
          var c = index[i].c || "Other";
          if (!catInfo[c]) catInfo[c] = { n: 0, slug: index[i].h || "" };
          catInfo[c].n += 1;
        }
      }
      return catInfo;
    }

    /* Site root, read off the form. Section links have to be absolute: the
       search page lives at /search/, so a relative "offices-coworking/" would
       resolve to /search/offices-coworking/ and 404. */
    var BASE = (form.getAttribute("data-base") || "/").replace(/\/*$/, "/");

    /* Category urls are hub slugs; only the category index is always safe to
       link, since a hub with too few listings has no page of its own. */
    function slugFor(title) {
      var info = catalogue()[title];
      return info && info.slug ? BASE + info.slug + "/" : BASE + "categories/";
    }

    /* Builds its own markup and escapes every interpolated value, so the
       caller must NOT escape the result again. */
    function sectionLinks(list) {
      var out = "";
      for (var i = 0; i < list.length; i += 1) {
        out += ' &middot; <a href="' + esc(slugFor(list[i].name)) + '">' +
               esc(list[i].name) + "</a>";
      }
      return out;
    }

    /* Strip diacritics before matching. "Décor" otherwise splits on the
       non-ASCII é into fragments, and the resulting one-letter fragment
       "d" prefix-matches "dentist" -- which is how a search for a dentist
       was being offered the furniture section. */
    function words(s) {
      return String(s).normalize("NFD").replace(/[̀-ͯ]/g, "")
        .toLowerCase().split(/[^a-z]+/).filter(function (w) {
          return w.length >= 3;
        });
    }

    function catalogueHint(q) {
      var terms = words(q);
      var cat = catalogue();

      if (terms.length) {
        var best = null;
        for (var name in cat) {
          var cw = words(name);
          for (var w = 0; w < cw.length; w += 1) {
            for (var t = 0; t < terms.length; t += 1) {
              /* stem-ish: first five letters catch "bakery"/"baker" */
              if (cw[w].indexOf(terms[t].slice(0, 5)) === 0 ||
                  terms[t].indexOf(cw[w].slice(0, 5)) === 0) {
                if (!best || cat[name].n > cat[best].n) best = name;
              }
            }
          }
        }
        if (best) {
          return "Nothing in the index matches that yet. The closest section " +
                 "is \"" + best + "\" (" + cat[best].n + " listings)" +
                 sectionLinks([{ name: best }]) + ".";
        }
      }

      var top = Object.keys(cat)
        .map(function (k) { return { name: k, n: cat[k].n }; })
        .sort(function (a, b) { return b.n - a.n; })
        .slice(0, 4);

      return "Nothing in the index matches that yet. The largest sections " +
             "are" + sectionLinks(top) +
             ", or search by suburb from the zones page.";
    }

    /* Rank order, strongest first: exact name, name prefix, name substring,
       the specific OSM type, the broad category, then the suburb. A business
       called "Woolworths" must outrank every shop in the Rivonia suburb. */
    function score(entry, q) {
      var name = entry.n.toLowerCase();
      if (name === q) return 0;
      if (name.indexOf(q) === 0) return 1;
      if (name.indexOf(q) > -1) return 2;
      if ((entry.k || "").toLowerCase().indexOf(q) > -1) return 3;
      if ((entry.c || "").toLowerCase().indexOf(q) > -1) return 4;
      if ((entry.z || "").toLowerCase().indexOf(q) > -1) return 5;
      return -1;
    }

    function render(q) {
      if (!index) return;

      var needle = q.trim().toLowerCase();
      if (!needle) {
        out.innerHTML = "";
        say("");
        return;
      }

      var hits = [];
      for (var i = 0; i < index.length; i += 1) {
        var s = score(index[i], needle);
        if (s > -1) hits.push({ e: index[i], s: s });
      }

      if (!hits.length) {
        /* catalogueHint returns markup with every value escaped inside it,
           so it is inserted directly rather than through esc(). */
        out.innerHTML =
          '<div class="search-empty"><b>Nothing matches "' + esc(q.trim()) +
          '"</b>' + catalogueHint(q) + "</div>";
        say('No matches for "' + q.trim() + '"');
        return;
      }

      hits.sort(function (a, b) {
        if (a.s !== b.s) return a.s - b.s;
        return a.e.n.length - b.e.n.length;
      });

      var LIMIT = 60;
      var shown = Math.min(hits.length, LIMIT);
      var html = "";
      for (var k = 0; k < shown; k += 1) {
        var e = hits[k].e;
        /* The OSM type is shown only when it adds something the category line
           above does not already say, so a result never reads as two labels
           for the same thing. Escaped like every other field -- the index is
           build-generated, but it is still data, not markup. */
        var kind = (e.k && e.k.toLowerCase() !== (e.c || "").toLowerCase())
          ? esc(e.k) + " &middot; " : "";
        html +=
          '<article class="result">' +
          '<div class="cat">' + esc(e.c) + "</div>" +
          '<h3><a href="' + esc(e.u) + '">' + mark(e.n, q.trim()) + "</a></h3>" +
          '<div class="meta">' + kind + esc(e.z) + "</div>" +
          '<a class="go" href="' + esc(e.u) + '">View &rarr;</a>' +
          "</article>";
      }
      out.innerHTML = html;

      say(
        shown === hits.length
          ? hits.length + (hits.length === 1 ? " match" : " matches")
          : "First " + shown + " of " + hits.length + " matches"
      );
    }

    function load(cb) {
      if (index) return cb();
      if (loading) return;
      loading = true;
      say("Loading the index...");

      var xhr = new XMLHttpRequest();
      xhr.open("GET", form.getAttribute("data-index"), true);
      xhr.onreadystatechange = function () {
        if (xhr.readyState !== 4) return;
        loading = false;
        if (xhr.status === 200 || xhr.status === 0) {
          try {
            index = JSON.parse(xhr.responseText);
          } catch (err) {
            index = null;
          }
        }
        if (index) cb();
        else say("Search is unavailable right now. Browse by category or suburb.");
      };
      xhr.send();
    }

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var q = input.value.trim();
      if (!q) return;
      load(function () {
        render(q);
        if (hints) hints.hidden = true;
      });
    });

    /* Live filtering as well as on submit, so the page feels immediate. */
    var t = null;
    input.addEventListener("input", function () {
      if (t) clearTimeout(t);
      t = setTimeout(function () {
        var q = input.value.trim();
        if (!q) {
          out.innerHTML = "";
          say("");
          if (hints) hints.hidden = false;
          return;
        }
        load(function () { render(q); });
      }, 140);
    });

    /* Honour ?q= so the JSON-LD SearchAction promise resolves to a real
       result set rather than an empty box. */
    var params = new URLSearchParams(window.location.search);
    var preset = params.get("q");
    if (preset) {
      input.value = preset;
      load(function () {
        render(preset);
        if (hints) hints.hidden = true;
      });
    }
  }

  function boot() {
    initNav();
    initFilters();
    initSearch();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();