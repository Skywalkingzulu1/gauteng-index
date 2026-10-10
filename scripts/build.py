#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py -- Generate the Gauteng Index static site.

The Gauteng Index is the parent directory of the Sandton Index: every
suburb-level place OpenStreetMap maps inside Gauteng, grouped by district,
with Sandton (covered in depth next door) linked as the child site.

Design rules inherited from the sandton-index build:
  - Only what the harvest measured is published. Suburb names, place types
    and coordinates come from data/gauteng_suburbs.json; nothing is
    invented to fill a page.
  - No thin pages: suburbs are listed on their district page, never given
    individual pages. A suburb name plus a coordinate is not a page.
  - Only CSS classes already defined in scripts/assets/sandton.css are
    emitted; the build fails otherwise (see verify below).
  - The one mapped place that reverse-geocodes outside Gauteng (Siyaya
    Lodge, Limpopo) stays in the data file for audit but gets no site
    page and no district card.

Usage: python scripts/build.py   (run from the repo root)
"""
import html
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
SITE = os.path.join(ROOT, "site")

SITE_URL = "https://skywalkingzulu1.github.io/gauteng-index"
SITE_NAME = "Gauteng Index"
SANDTON_URL = "https://skywalkingzulu1.github.io/sandton-index"
ASSET_VERSION = "v1"

# Districts published as pages, in display order. Keys must match the
# "district" values in data/gauteng_suburbs.json exactly.
DISTRICTS = [
    ("city-of-johannesburg-metropolitan-municipality",
     "City of Johannesburg"),
    ("city-of-ekurhuleni-metropolitan-municipality",
     "City of Ekurhuleni"),
    ("city-of-tshwane-metropolitan-municipality",
     "City of Tshwane"),
    ("sedibeng-district-municipality",
     "Sedibeng"),
    ("west-rand-district-municipality",
     "West Rand"),
]


def e(value):
    return html.escape(str(value if value is not None else ""))


def asset_url(name):
    return f"{SITE_URL}/assets/{name}?v={ASSET_VERSION}"


def header_html():
    return f"""<header class="site"><div class="wrap">
<a class="brand" href="{SITE_URL}/"><span class="mark">GI</span>
<span>Gauteng <b>Index</b></span></a>
<nav class="site" id="si-nav">
<a href="{SITE_URL}/">Home</a>
<a href="{SITE_URL}/districts/">Districts</a>
<a href="{SANDTON_URL}/">Sandton Index</a>
<a class="nav-cta" href="{SANDTON_URL}/dashboard/">No-website dashboard</a>
</nav>
<button class="nav-toggle" id="si-nav-toggle" type="button"
 aria-expanded="false" aria-controls="si-nav" aria-label="Open menu">
<span></span></button>
</div></header>"""


def footer_html(districts):
    links = "".join(
        f'<a href="{SITE_URL}/districts/{slug}/">{e(short)}</a>'
        for slug, short in districts)
    return f"""<footer class="site"><div class="wrap">
<div class="foot-grid">
<div class="foot-brand">
<h4><span class="mark">GI</span> Gauteng Index</h4>
<p>Every suburb-level place mapped in Gauteng, South Africa &mdash; the
parent directory of the Sandton Index.</p>
</div>
<div class="foot-col">
<h5>Districts</h5>
{links}
</div>
<div class="foot-col">
<h5>Child site</h5>
<a href="{SANDTON_URL}/">Sandton Index</a>
<a href="{SANDTON_URL}/dashboard/">No-website dashboard</a>
<a href="{SANDTON_URL}/search/">Search Sandton</a>
</div>
</div>
<div class="foot-bottom">
<span>&copy; 2026 Gauteng Index. Map data &copy; OpenStreetMap contributors.</span>
<span>Suburb names and coordinates via OpenStreetMap.</span>
</div>
</div></footer>"""


def page(title, description, body, canonical):
    return f"""<!doctype html>
<html lang="en-ZA">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{e(canonical)}">
<meta name="theme-color" content="#0052cc">
<meta name="geo.region" content="ZA-GT">
<meta name="geo.placename" content="Gauteng, South Africa">
<link rel="stylesheet" href="{asset_url('sandton.css')}">
</head>
<body>
<a class="skip-link" href="#si-main">Skip to content</a>
{header_html()}
<main id="si-main">
{body}
</main>
{footer_html(DISTRICTS)}
<script defer src="{asset_url('sandton.js')}"></script>
</body></html>
"""


def finder_html(scope, placeholder, target):
    return f"""<div class="finder">
<input type="search" class="si-q" data-target="{e(target)}"
 placeholder="{e(placeholder)}" aria-label="{e(scope)}">
<span class="si-count" aria-live="polite"></span>
<span class="si-none" hidden>No places match that. Try a shorter word.</span>
</div>"""


def write(path_rel, content):
    full = os.path.join(SITE, path_rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)


def emit_assets():
    dest = os.path.join(SITE, "assets")
    os.makedirs(dest, exist_ok=True)
    for name in ("sandton.css", "sandton.js"):
        shutil.copyfile(os.path.join(HERE, "assets", name),
                        os.path.join(dest, name))


def schema_website():
    return ('<script type="application/ld+json">{"@context": '
            '"https://schema.org", "@type": "WebSite", "name": '
            f'"{SITE_NAME}", "url": "{SITE_URL}/"}}</script>')


def build_home(by_district, total):
    cards = "".join(
        f"""<article class="card">
<div class="cat">{len(by_district[slug])} places mapped</div>
<h3><a href="{SITE_URL}/districts/{e(slug)}/">{e(short)}</a></h3>
<div class="meta">Suburbs, neighbourhoods, villages and towns</div>
<div class="acts"><a href="{SITE_URL}/districts/{e(slug)}/">Browse &rarr;</a></div>
</article>""" for slug, short in DISTRICTS)
    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> Gauteng, South Africa</div>
<h1>Every suburb in Gauteng,<br><span class="grad">on one map</span></h1>
<p>{total} suburb-level places across {len(DISTRICTS)} districts, mapped
from OpenStreetMap. Sandton is covered in depth on the child site.</p>
<div class="hero-actions">
<a class="btn" href="{SITE_URL}/districts/">Browse districts</a>
<a class="btn-2" href="{SANDTON_URL}/">Sandton Index</a>
</div>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<div class="stats">
<div class="stat"><div class="stat-ico ico-blue">&#127978;</div>
<b>{total}</b><span>Places mapped</span></div>
<div class="stat"><div class="stat-ico ico-teal">&#128205;</div>
<b>{len(DISTRICTS)}</b><span>Districts</span></div>
<div class="stat"><div class="stat-ico ico-green">&#128272;</div>
<b>1</b><span>Child site</span></div>
</div>
<h2 class="sec">Browse by district</h2>
<div class="grid">{cards}</div>
<div class="cta">
<h2>Sandton is covered in depth next door.</h2>
<p>660 businesses with hours, maps and contact details -- plus the
no-website dashboard.</p>
<a class="btn" href="{SANDTON_URL}/">Open the Sandton Index</a>
</div>
</div>"""
    write("index.html", page(
        f"{SITE_NAME} | Every suburb in Gauteng, South Africa",
        f"{total} Gauteng suburbs, neighbourhoods, villages and towns "
        f"across {len(DISTRICTS)} districts, mapped from OpenStreetMap.",
        body, f"{SITE_URL}/"))


def build_districts_index(by_district, total):
    cards = "".join(
        f"""<article class="card">
<div class="cat">{len(by_district[slug])} places mapped</div>
<h3><a href="{SITE_URL}/districts/{e(slug)}/">{e(short)}</a></h3>
<div class="meta">Gauteng, South Africa</div>
<div class="acts"><a href="{SITE_URL}/districts/{e(slug)}/">Browse &rarr;</a></div>
</article>""" for slug, short in DISTRICTS)
    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> {total} places</div>
<h1>Districts</h1>
<p>The five district and metropolitan municipalities of Gauteng. Pick one,
then a suburb.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<h2 class="sec">All districts</h2>
<div class="grid">{cards}</div></div>"""
    write(os.path.join("districts", "index.html"), page(
        f"Districts | {SITE_NAME}",
        "The five districts of Gauteng with every mapped suburb.",
        body, f"{SITE_URL}/districts/"))


def build_district(slug, short, suburbs):
    subs = sorted(suburbs, key=lambda s: s["name"].lower())
    child_note = ""
    if slug == "city-of-johannesburg-metropolitan-municipality":
        child_note = f"""<div class="cta">
<h2>Sandton businesses are indexed next door.</h2>
<p>350 Sandton listings matched to Johannesburg suburbs -- browse them
all, including the no-website dashboard, on the child site.</p>
<a class="btn" href="{SANDTON_URL}/dashboard/">Open the dashboard</a>
</div>"""
    else:
        child_note = """<div class="cta">
<h2>Business listings stop at Sandton for now.</h2>
<p>These suburbs are mapped ground for expansion, not indexed content.
The child site covers Sandton in depth today.</p>
<a class="btn" href="{SANDTON_URL}/">Open the Sandton Index</a>
</div>"""
    cards = "".join(
        f"""<article class="card">
<div class="cat">{e(s['place'])}</div>
<h3>{e(s['name'])}</h3>
<div class="meta">{e(s['municipality'])} &middot; {s['lat']}, {s['lon']}</div>
</article>""" for s in subs)
    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> Gauteng</div>
<h1>{e(short)}</h1>
<p>{len(subs)} suburb-level places mapped from OpenStreetMap.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<div class="crumb"><a href="{SITE_URL}/">Home</a> &rsaquo;
<a href="{SITE_URL}/districts/">Districts</a> &rsaquo; {e(short)}</div>
<h2 class="sec">All {len(subs)} places</h2>
{finder_html("Filter places", "Type a suburb name", "si-sub-grid")}
<div class="grid" id="si-sub-grid">{cards}</div>
{child_note}
</div>"""
    write(os.path.join("districts", slug, "index.html"), page(
        f"{short} suburbs | {SITE_NAME}",
        f"{len(subs)} suburbs, neighbourhoods, villages and towns in "
        f"{short}, Gauteng, mapped from OpenStreetMap.",
        body, f"{SITE_URL}/districts/{slug}/"))


def build_sitemap(urls):
    parts = [f"<url><loc>{u}</loc></url>" for u in urls]
    write("sitemap.xml",
          '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(parts) + "</urlset>")


def verify():
    """Fail the build on anything unsafe to publish."""
    failures = []
    pages = []
    for root, _dirs, files in os.walk(SITE):
        for f in files:
            if f == "index.html":
                pages.append(os.path.join(root, f))
    link_re = re.compile(r'href="(/[^"#?]*)"')
    for p in pages:
        html = open(p, encoding="utf-8").read()
        if not re.search(r"<title>(.*?)</title>", html, re.S) \
                or 'name="description"' not in html \
                or 'rel="canonical"' not in html:
            failures.append(f"{p}: missing title/description/canonical")
        if "<style>" in html:
            failures.append(f"{p}: inline <style>")
        if "{}" in html or "{e(" in html:
            failures.append(f"{p}: template leak")
        for href in link_re.findall(html):
            rel = href.strip("/")
            if rel and not os.path.exists(
                    os.path.join(SITE, rel, "index.html")):
                failures.append(f"{p}: broken link {href}")
    if "sandton.css" not in open(
            os.path.join(SITE, "index.html"), encoding="utf-8").read():
        failures.append("home does not link the stylesheet")
    for name in ("sandton.css", "sandton.js"):
        if not os.path.exists(os.path.join(SITE, "assets", name)):
            failures.append(f"site/assets/{name} missing")
    # every emitted class must exist in the stylesheet
    css = open(os.path.join(SITE, "assets", "sandton.css"),
               encoding="utf-8").read()
    for p in pages:
        html = open(p, encoding="utf-8").read()
        for cls in set(re.findall(r'class="([^"]+)"', html)):
            for c in cls.split():
                if c not in ("wrap",) and f".{c}" not in css \
                        and not c.startswith("fa-"):
                    failures.append(f"{p}: class .{c} has no rule")
                    break
    if failures:
        print("VERIFY FAILED:")
        for f in failures[:15]:
            print("  x", f)
        sys.exit(1)
    print(f"verify: {len(pages)} pages, all checks passed")


def main():
    with open(os.path.join(DATA, "gauteng_suburbs.json"),
              encoding="utf-8") as fh:
        suburbs = json.load(fh)["suburbs"]
    by_district = {slug: [] for slug, _short in DISTRICTS}
    slug_by_prefix = {
        "City of Johannesburg": DISTRICTS[0][0],
        "City of Ekurhuleni": DISTRICTS[1][0],
        "City of Tshwane": DISTRICTS[2][0],
        "Sedibeng": DISTRICTS[3][0],
        "West Rand": DISTRICTS[4][0],
    }
    outside = 0
    for s in suburbs:
        for prefix, slug in slug_by_prefix.items():
            if (s.get("district") or "").startswith(prefix):
                by_district[slug].append(s)
                break
        else:
            outside += 1
    if outside:
        print(f"note: {outside} mapped places fall outside the five "
              f"districts (kept in data, no site page)")
    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE, exist_ok=True)
    emit_assets()
    build_home(by_district, sum(len(v) for v in by_district.values()))
    build_districts_index(by_district,
                          sum(len(v) for v in by_district.values()))
    for slug, short in DISTRICTS:
        build_district(slug, short, by_district[slug])
    write("404.html", page(
        "Page not found | Gauteng Index",
        "That page does not exist.",
        f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> 404</div>
<h1>That page is not<br>in the <span class="grad">index</span></h1>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<div class="grid">
<article class="card">
<h3><a href="{SITE_URL}/">Home</a></h3>
<div class="acts"><a href="{SITE_URL}/">Browse &rarr;</a></div>
</article>
<article class="card">
<h3><a href="{SANDTON_URL}/">Sandton Index</a></h3>
<div class="acts"><a href="{SANDTON_URL}/">Open &rarr;</a></div>
</article>
</div></div>""",
        f"{SITE_URL}/404.html"))
    with open(os.path.join(SITE, "robots.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("User-agent: *\nAllow: /\nSitemap: "
                 f"{SITE_URL}/sitemap.xml\n")
    written = []
    for root, _dirs, files in os.walk(SITE):
        for f in files:
            if f == "index.html":
                rel = os.path.relpath(os.path.join(root, f), SITE)
                written.append(rel.replace("\\", "/"))
    build_sitemap(sorted(f"{SITE_URL}/{w[:-len('/index.html')]}/"
                         if w != "index.html" else f"{SITE_URL}/"
                         for w in written))
    print(f"built {len(written)} pages")
    verify()


if __name__ == "__main__":
    main()
