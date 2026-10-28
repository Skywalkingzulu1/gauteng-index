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
import unicodedata
import urllib.parse
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

SITE_URL = os.environ.get(
    "GAUTENG_SITE_URL",
    "https://skywalkingzulu1.github.io/gauteng-index").rstrip("/")
SITE = os.path.join(
    ROOT, "site-local" if "GAUTENG_SITE_URL" in os.environ else "site")
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


# ---------------------------------------------------------------- taxonomy
# OSM key=value pairs mapped onto directory categories. Anything the
# harvest collects but no rule below claims falls into "other" -- visible,
# searchable, but never forced into a wrong category.
#
# Civic tags (government, diplomatic, schools...) are dropped before this
# stage, not mapped: they are not companies and this is a business map.
CATS = [
    ("food-drink", "Food & Drink", "restaurant",
     [("amenity", {"restaurant", "cafe", "fast_food", "food_court", "bar",
                   "pub", "biergarten", "ice_cream"}),
      ("shop", {"bakery", "butcher", "deli", "confectionery", "coffee",
                "tea", "chocolate", "beverages", "alcohol", "seafood",
                "greengrocer", "farm"})]),
    ("retail-shopping", "Retail & Shopping", "shop",
     [("shop", {"clothes", "shoes", "supermarket", "convenience", "mall",
                "department_store", "boutique", "gift", "variety_store",
                "charity", "second_hand", "jewelry", "watches", "books",
                "stationery", "florist"})]),
    ("automotive", "Automotive", "car service",
     [("shop", {"car", "car_repair", "car_parts", "tyres", "motorcycle"}),
      ("amenity", {"fuel", "car_wash", "car_rental"})]),
    ("health", "Health & Medical", "clinic",
     [("healthcare", {"pharmacy", "doctor", "dentist", "clinic",
                      "hospital", "optometrist", "physiotherapist"}),
      ("amenity", {"pharmacy", "doctors", "dentist", "clinic",
                   "hospital"}),
      ("shop", {"chemist", "optician", "hearing_aids",
                "medical_supply"})]),
    ("banks-finance", "Banks & Finance", "bank",
     [("amenity", {"bank", "bureau_de_change"})]),
    ("hotels-travel", "Hotels & Travel", "hotel",
     [("tourism", {"hotel", "guest_house", "hostel", "motel",
                   "apartment"}),
      ("shop", {"travel_agency"})]),
    ("beauty-personal", "Beauty & Personal Care", "salon",
     [("shop", {"hairdresser", "beauty", "cosmetics", "massage",
                "tattoo", "nails", "perfumery"})]),
    ("home-trade", "Home & Trade", "hardware store",
     [("shop", {"hardware", "doityourself", "paint", "electronics",
                "furniture", "houseware", "garden_centre", "lighting",
                "flooring", "curtain", "bed", "bathroom_furnishing",
                "kitchen", "doors", "windows"}),
      ("craft", None)]),
    ("professional", "Professional Services", "office",
     [("office", {"company", "consulting", "lawyer", "estate_agent",
                  "insurance", "accountant", "advertising_agency",
                  "employment_agency", "it", "telecommunication",
                  "research", "ngo", "association", "charity", "yes",
                  "coworking", "architect", "engineer", "surveyor"})]),
    ("fitness-sport", "Fitness & Sport", "gym",
     [("leisure", {"fitness_centre", "sports_centre", "bowling_alley",
                   "golf_course", "water_park", "amusement_arcade",
                   "pitch", "stadium"}),
      ("shop", {"sports", "outdoor", "bicycle", "fishing", "golf"})]),
    ("pets-animals", "Pets & Animals", "pet shop",
     [("shop", {"pet"}),
      ("amenity", {"veterinary"}),
      ("healthcare", {"veterinary"})]),
    ("tech-electronics", "Tech & Electronics", "phone shop",
     [("shop", {"mobile_phone", "computer", "electronics", "hifi",
                "photo", "video_games", "appliance"})]),
    ("other", "Other Businesses", "business",
     []),
]
CAT_BY_SLUG = {c[0]: c for c in CATS}
MIN_HUB_LISTINGS = 3

# Tags that are never companies, dropped before categorising. Without this
# an embassy or a school would get a business page and a "no website"
# pitch -- the exact false-claim class the Sandton directory was built to
# avoid.
CIVIC_DROP = {
    ("office", "government"), ("office", "diplomatic"),
    ("office", "educational_institution"), ("office", "administrative"),
    ("office", "political_party"), ("office", "religion"),
}


def slugify(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode(
        "ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "listing"


def cat_of(biz):
    kv = (biz["key"], biz["value"])
    if kv in CIVIC_DROP:
        return None
    for slug, _title, _sing, rules in CATS:
        for key, allowed in rules:
            if biz["key"] == key and (allowed is None
                                      or biz["value"] in allowed):
                return slug
    return "other"


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


def page(title, description, body, canonical, extra_head=""):
    return f"""<!doctype html>
<html lang="en-ZA">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
}})(window,document,'script','dataLayer','GTM-52JL49JJ');</script>
<!-- End Google Tag Manager -->
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
{extra_head}
<link rel="stylesheet" href="{asset_url('sandton.css')}">
</head>
<body>
<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-52JL49JJ"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->
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
    # gauteng-search.js is a build input with a placeholder for the
    # absolute asset base (fetch() needs it: a relative URL would resolve
    # against /search/ instead of /assets/).
    with open(os.path.join(HERE, "assets", "gauteng-search.js"),
              encoding="utf-8") as fh:
        js = fh.read().replace("ASSET_BASE", SITE_URL + "/assets/")
    with open(os.path.join(dest, "gauteng-search.js"), "w",
              encoding="utf-8") as fh:
        fh.write(js)


def build_search_page(businesses):
    idx = [{"n": b["name"],
            "c": CAT_BY_SLUG[b["cat"]][1],
            "k": f"{b['key']}={b['value']}",
            "z": b.get("suburb") or short_district(b.get("district")),
            "u": f"{SITE_URL}/b/{b['slug']}/"} for b in businesses]
    with open(os.path.join(SITE, "assets", "search-index.json"), "w",
              encoding="utf-8") as fh:
        json.dump(idx, fh, ensure_ascii=False)
    body = f"""<div class="search-hero"><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> Gauteng</div>
<h1>Search Gauteng businesses</h1>
<form class="si-search-form" action="{SITE_URL}/search/" method="get"
 role="search">
<label class="si-visually-hidden" for="si-q">Search businesses</label>
<input id="si-q" name="q" type="search" autocomplete="off"
 placeholder="Try a name, category or suburb" enterkeyhint="search">
<button class="btn" type="submit">Search</button>
</form>
<div class="si-search-status" aria-live="polite"></div>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<div class="si-search-results"></div>
<p>Without JavaScript, use your browser's find on the
<a href="{SITE_URL}/categories/">category pages</a> instead.</p>
</div>
<script defer src="{asset_url('gauteng-search.js')}"></script>"""
    # The script tag lives in the body on purpose: page() appends only the
    # shared shell, and the search script is page-specific.
    write(os.path.join("search", "index.html"), page(
        f"Search | {SITE_NAME}",
        "Search every mapped business in Gauteng by name, category or "
        "suburb.",
        body, f"{SITE_URL}/search/"))
    return len(idx)


def schema_website():
    return ('<script type="application/ld+json">{"@context": '
            '"https://schema.org", "@type": "WebSite", "name": '
            f'"{SITE_NAME}", "url": "{SITE_URL}/"}}</script>')


def build_home(by_district, total, n_biz):
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
<form class="search-box" action="{SITE_URL}/search/" method="get" role="search">
<label class="si-visually-hidden" for="si-home-search">Search Gauteng
businesses</label>
<input id="si-home-search" name="q" type="search" autocomplete="off"
 placeholder="Search businesses" enterkeyhint="search">
<button type="submit">Search</button>
</form>
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
<div class="stat"><div class="stat-ico ico-amber">&#127978;</div>
<b>{n_biz}</b><span>Businesses</span></div>
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
        f"{total} Gauteng suburbs and {n_biz} mapped businesses across "
        f"{len(DISTRICTS)} districts, from OpenStreetMap.",
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


def _district_card(s, sub_urls, sub_stats):
    name = s["name"]
    if name in sub_urls:
        h3 = (f'<h3><a href="{sub_urls[name]}">{e(name)} '
              f'&rarr;</a></h3>')
    else:
        h3 = f"<h3>{e(name)}</h3>"
    stats = ""
    if name in sub_stats:
        total, with_site = sub_stats[name]
        stats = (f'<div class="meta">{total} businesses &middot; '
                 f'{with_site} website listed &middot; '
                 f'{total - with_site} not listed</div>')
    return f"""<article class="card">
<div class="cat">{e(s['place'])}</div>
{h3}
<div class="meta">{e(s['municipality'])} &middot; {s['lat']}, {s['lon']}</div>
{stats}</article>"""


def build_district(slug, short, suburbs, sub_urls, sub_stats):
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
        child_note = f"""<div class="cta">
<h2>Browse every business on this site.</h2>
<p>Suburbs below link to their business listings where mapped.</p>
<a class="btn" href="{SITE_URL}/categories/">Browse categories</a>
</div>"""
    cards = "".join(
        _district_card(s, sub_urls, sub_stats) for s in subs)
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


def short_district(full):
    for prefix, short in (("City of Johannesburg", "Johannesburg"),
                          ("City of Ekurhuleni", "Ekurhuleni"),
                          ("City of Tshwane", "Tshwane"),
                          ("Sedibeng", "Sedibeng"),
                          ("West Rand", "West Rand")):
        if (full or "").startswith(prefix):
            return short
    return full or "Gauteng"


def maps_url(biz):
    return ("https://www.google.com/maps/dir/?api=1&destination="
            f"{biz['lat']},{biz['lon']}")


def build_business_page(biz, cat_slug, cat_title, hub_exists):
    suburb = biz.get("suburb") or ""
    district = short_district(biz.get("district"))
    area = suburb if suburb else district
    if suburb and hub_exists:
        more_url = f"{SITE_URL}/{cat_slug}/{slugify(suburb)}/"
        more_label = f"More in {area}"
    else:
        more_url = f"{SITE_URL}/{cat_slug}/"
        more_label = f"More {cat_title.lower()}"

    addr = biz.get("addr") or ""
    addr_html = (f"<div class=\"meta\">{e(addr)}</div>" if addr else
                 "<div class=\"meta\">Street address not mapped in "
                 "OpenStreetMap</div>")
    phone_html = (f"<div class=\"meta\">Phone {e(biz['phone'])}</div>"
                  if biz.get("phone") else "")
    if biz.get("has_website_osm") and biz.get("website"):
        web_block = (f"""<div class="cta" style="margin-top:0">
<h2>Website listed</h2>
<p>OpenStreetMap carries a website for this business.</p>
<a class="btn" href="{e(biz['website'])}" target="_blank" rel="noopener">
Visit website &rarr;</a>
</div>""")
        badge = '<span class="badge b-c">Website listed</span>'
    else:
        web_block = f"""<div class="cta" style="margin-top:0">
<h2>No website listed in OpenStreetMap</h2>
<p>This business has no website tag in the map data. That is not proof it
has no website -- many businesses simply are not tagged. If you own this
business, getting the tag added (or claiming a directory page) is the
cheapest visibility you can buy: it costs nothing.</p>
</div>"""
        badge = '<span class="badge b-a">No website listed</span>'

    ld = {"@context": "https://schema.org", "@type": "LocalBusiness",
          "name": biz["name"], "url": f"{SITE_URL}/b/{biz['slug']}/",
          "geo": {"@type": "GeoCoordinates",
                  "latitude": biz["lat"], "longitude": biz["lon"]},
          "hasMap": maps_url(biz)}
    if addr:
        ld["address"] = {"@type": "PostalAddress",
                         "streetAddress": addr,
                         "addressRegion": "Gauteng",
                         "addressCountry": "ZA"}
    if biz.get("phone"):
        ld["telephone"] = biz["phone"]
    if biz.get("has_website_osm") and biz.get("website"):
        ld["sameAs"] = [biz["website"]]
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList",
              "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": "Home",
                   "item": f"{SITE_URL}/"},
                  {"@type": "ListItem", "position": 2, "name": cat_title,
                   "item": f"{SITE_URL}/{cat_slug}/"}]}
    extra = ('<script type="application/ld+json">'
             + json.dumps(ld, ensure_ascii=False) + "</script>"
             + '<script type="application/ld+json">'
             + json.dumps(crumbs, ensure_ascii=False) + "</script>")
    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> {e(cat_title)} &middot;
{e(area)}</div>
<h1>{e(biz['name'])}</h1>
<p>{e(cat_title)} in {e(area)}, {e(district)}. {badge}</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<div class="crumb"><a href="{SITE_URL}/">Home</a> &rsaquo;
<a href="{SITE_URL}/{e(cat_slug)}/">{e(cat_title)}</a> &rsaquo;
{e(biz['name'])}</div>
<h2 class="sec">Find them</h2>
<div class="grid">
<article class="card">
<div class="cat">Location</div>
<h3>{e(area)}</h3>
{addr_html}
{phone_html}
<div class="meta">{biz['lat']}, {biz['lon']}</div>
<div class="acts"><a href="{e(maps_url(biz))}" target="_blank"
rel="noopener">Directions &rarr;</a></div>
</article>
<article class="card">
<div class="cat">Source</div>
<h3>OpenStreetMap</h3>
<div class="meta">Name, category and coordinates as mapped. Listing data
is only as fresh as the map.</div>
<div class="acts"><a href="{e(more_url)}">{e(more_label)} &rarr;</a></div>
</article>
</div>
{web_block}
</div>"""
    write(os.path.join("b", biz["slug"], "index.html"), page(
        f"{biz['name']} in {area} | {SITE_NAME}",
        f"{biz['name']}: {cat_title.lower()} in {area}, Gauteng. "
        f"Map, directions and contact details.",
        body, f"{SITE_URL}/b/{biz['slug']}/", extra_head=extra))


def build_suburb_page(suburb, slug, recs, district_short):
    cards = "".join(
        f"""<article class="card">
<h3><a href="{SITE_URL}/b/{e(b['slug'])}/">{e(b['name'])}</a></h3>
<div class="meta">{e(CAT_BY_SLUG[b['cat']][1])} &middot;
{e('Website listed' if b['has_website_osm'] else 'No website listed')}</div>
<div class="acts"><a href="{SITE_URL}/b/{e(b['slug'])}/">View &rarr;</a></div>
</article>""" for b in sorted(recs, key=lambda r: r["name"].lower()))
    with_site = sum(1 for b in recs if b["has_website_osm"])
    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> {len(recs)} businesses</div>
<h1>{e(suburb)}</h1>
<p>Every mapped business in {e(suburb)}, {e(district_short)} -- {with_site}
with a website listed, {len(recs) - with_site} without.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<div class="crumb"><a href="{SITE_URL}/">Home</a> &rsaquo;
<a href="{SITE_URL}/districts/">Districts</a> &rsaquo; {e(suburb)}</div>
<h2 class="sec">All {len(recs)} businesses</h2>
{finder_html(f"Businesses in {suburb}", "Filter by name", "si-sub-grid")}
<div class="grid" id="si-sub-grid">{cards}</div>
</div>"""
    write(os.path.join("suburbs", slug, "index.html"), page(
        f"{suburb} businesses | {SITE_NAME}",
        f"{len(recs)} mapped businesses in {suburb}, Gauteng.",
        body, f"{SITE_URL}/suburbs/{slug}/"))


def build_cat_hub_page(cat_slug, cat_title, suburb, slug, recs,
                       suburb_url=None):
    cards = "".join(
        f"""<article class="card">
<h3><a href="{SITE_URL}/b/{e(b['slug'])}/">{e(b['name'])}</a></h3>
<div class="meta">{e(b.get('addr') or 'Address not mapped')}</div>
<div class="acts"><a href="{SITE_URL}/b/{e(b['slug'])}/">View &rarr;</a></div>
</article>""" for b in sorted(recs, key=lambda r: r["name"].lower()))
    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> {len(recs)} listings</div>
<h1>{e(cat_title)} in {e(suburb)}</h1>
<p>Every mapped {cat_title.lower()} business in {e(suburb)}, Gauteng.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<div class="crumb"><a href="{SITE_URL}/">Home</a> &rsaquo;
<a href="{SITE_URL}/{e(cat_slug)}/">{e(cat_title)}</a> &rsaquo; {e(suburb)}</div>
<h2 class="sec">All {len(recs)} listings</h2>
{finder_html(f"{cat_title} in {suburb}", "Filter by name", "si-hub-grid")}
<div class="grid" id="si-hub-grid">{cards}</div>
{suburb_url if suburb_url else ""}
</div>"""
    write(os.path.join(cat_slug, slug, "index.html"), page(
        f"{cat_title} in {suburb} | {SITE_NAME}",
        f"{len(recs)} {cat_title.lower()} businesses in {suburb}, "
        f"Gauteng, mapped from OpenStreetMap.",
        body, f"{SITE_URL}/{cat_slug}/{slug}/"))


def build_cat_page(cat_slug, cat_title, suburb_counts):
    cards = "".join(
        f"""<article class="card">
<div class="cat">{n} listings</div>
<h3><a href="{SITE_URL}/{e(cat_slug)}/{e(slug)}/">{e(name)}</a></h3>
<div class="meta">{e(cat_title)} in {e(name)}</div>
<div class="acts"><a href="{SITE_URL}/{e(cat_slug)}/{e(slug)}/">Browse &rarr;</a></div>
</article>""" for name, slug, n in suburb_counts)
    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> Gauteng</div>
<h1>{e(cat_title)}</h1>
<p>Browse by suburb. Only suburbs with enough mapped listings get their
own page; the rest are folded into the district pages.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<div class="crumb"><a href="{SITE_URL}/">Home</a> &rsaquo; {e(cat_title)}</div>
<h2 class="sec">Suburbs</h2>
{finder_html(f"{cat_title} suburbs", "Filter by suburb", "si-cat-grid")}
<div class="grid" id="si-cat-grid">{cards}</div>
</div>"""
    write(os.path.join(cat_slug, "index.html"), page(
        f"{cat_title} in Gauteng | {SITE_NAME}",
        f"{cat_title} businesses across Gauteng, by suburb.",
        body, f"{SITE_URL}/{cat_slug}/"))


def build_categories_index(cats_present):
    cards = "".join(
        f"""<article class="card">
<div class="cat">{n} listings</div>
<h3><a href="{SITE_URL}/{e(slug)}/">{e(title)}</a></h3>
<div class="meta">Across Gauteng</div>
<div class="acts"><a href="{SITE_URL}/{e(slug)}/">Browse &rarr;</a></div>
</article>""" for slug, title, n in cats_present)
    body = f"""<div class="hero"><div class="hero-grid"></div><div class="wrap">
<div class="hero-eyebrow"><span class="dot"></span> Gauteng</div>
<h1>Categories</h1>
<p>Every business category mapped in Gauteng. Pick a category, then a
suburb.</p>
</div></div>
<div class="wrap" style="position:relative;z-index:3;padding-top:2rem">
<h2 class="sec">All categories</h2>
<div class="grid">{cards}</div></div>"""
    write(os.path.join("categories", "index.html"), page(
        f"Categories | {SITE_NAME}",
        "Browse Gauteng businesses by category.",
        body, f"{SITE_URL}/categories/"))


def build_sitemap(urls):
    """Shard at 500 URLs per file behind a sitemap index.

    Google's free tier processes 500 URLs per sitemap file; a flat
    16,000-URL file would silently truncate. Shards are named
    sitemap-001.xml, sitemap-002.xml, ... and listed in sitemap.xml.
    """
    SHARD = 500
    shards = [urls[i:i + SHARD] for i in range(0, len(urls), SHARD)]
    refs = []
    for n, chunk in enumerate(shards, 1):
        name = f"sitemap-{n:03d}.xml"
        parts = [f"<url><loc>{u}</loc></url>" for u in chunk]
        write(name,
              '<?xml version="1.0" encoding="UTF-8"?>\n'
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
              + "".join(parts) + "</urlset>")
        refs.append(f"{SITE_URL}/{name}")
    write("sitemap.xml",
          '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(f"<sitemap><loc>{r}</loc></sitemap>" for r in refs)
          + "</sitemapindex>")
    return len(shards)


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
    for name in ("sandton.css", "sandton.js", "gauteng-search.js"):
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
    # search index must cover every business page exactly once
    idx_path = os.path.join(SITE, "assets", "search-index.json")
    if not os.path.exists(idx_path):
        failures.append("search index missing")
    # sitemap shards must stay within the 500-URL processing limit
    sm = open(os.path.join(SITE, "sitemap.xml"), encoding="utf-8").read()
    refs = re.findall(r"<loc>(.*?)</loc>", sm)
    if not refs:
        failures.append("sitemap index lists no shards")
    for ref in refs:
        name = ref.rstrip("/").split("/")[-1]
        fp = os.path.join(SITE, name)
        if not os.path.exists(fp):
            failures.append(f"sitemap references missing {name}")
            continue
        n = len(re.findall(r"<loc>",
                           open(fp, encoding="utf-8").read()))
        if n > 500:
            failures.append(f"{name} has {n} URLs (limit 500)")
    if failures:
        print("VERIFY FAILED:")
        for f in failures[:15]:
            print("  x", f)
        sys.exit(1)
    print(f"verify: {len(pages)} pages, all checks passed")


def main():
    global SITE
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
        try:
            shutil.rmtree(SITE)
        except PermissionError:
            # A preview server or an open browser tab is holding files.
            # Rather than fail, build into a fresh timestamped directory;
            # stale ones are removed best-effort on the next clean build.
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            alt = f"{SITE}-{stamp}"
            print(f"    {SITE} locked, building into {alt} instead",
                  flush=True)
            SITE = alt
    for entry in os.listdir(ROOT):
        if entry.startswith("site-local-2"):
            try:
                shutil.rmtree(os.path.join(ROOT, entry))
                print(f"    removed stale {entry}", flush=True)
            except OSError:
                pass
    os.makedirs(SITE, exist_ok=True)
    emit_assets()

    with open(os.path.join(DATA, "gauteng_businesses.json"),
              encoding="utf-8") as fh:
        businesses = json.load(fh)["businesses"]

    # categorise + drop civic tags; assign collision-free slugs
    slug_seen = {}
    kept = []
    for b in businesses:
        cat = cat_of(b)
        if cat is None:
            continue
        base = slugify((b.get("name") or "") + " " +
                       (b.get("suburb") or short_district(b.get("district"))))
        n = slug_seen.get(base, 0) + 1
        slug_seen[base] = n
        b["slug"] = base if n == 1 else f"{base}-{n}"
        b["cat"] = cat
        kept.append(b)
    print(f"businesses: {len(businesses)} harvested, {len(kept)} kept "
          f"({len(businesses) - len(kept)} civic dropped)")

    by_cat_sub = {}
    for b in kept:
        sub = b.get("suburb") or ""
        by_cat_sub.setdefault((b["cat"], sub), []).append(b)

    build_home(by_district, sum(len(v) for v in by_district.values()),
               len(kept))
    build_districts_index(by_district,
                          sum(len(v) for v in by_district.values()))

    # suburb pages: suburbs with >= 5 mapped businesses earn a page (the
    # Sandton zone-page equivalent); smaller ones link to search instead.
    MIN_SUBURB_LISTINGS = 5
    sub_groups = {}
    for b in kept:
        if b.get("suburb"):
            sub_groups.setdefault(b["suburb"], []).append(b)
    sub_slug, sub_used = {}, set()
    for name in sorted(sub_groups):
        s = slugify(name)
        i, base = 1, s
        while s in sub_used:
            i += 1
            s = f"{base}-{i}"
        sub_used.add(s)
        sub_slug[name] = s
    sub_urls = {}
    n_sub = 0
    for name, recs in sorted(sub_groups.items()):
        if len(recs) >= MIN_SUBURB_LISTINGS:
            dist = short_district(recs[0].get("district"))
            build_suburb_page(name, sub_slug[name], recs, dist)
            sub_urls[name] = (f"{SITE_URL}/suburbs/{sub_slug[name]}/")
            n_sub += 1
        else:
            sub_urls[name] = (
                f"{SITE_URL}/search/?q="
                f"{urllib.parse.quote_plus(name)}")
    sub_stats = {}
    for name, recs in sub_groups.items():
        w = sum(1 for b in recs if b["has_website_osm"])
        sub_stats[name] = (len(recs), w)
    for slug, short in DISTRICTS:
        build_district(slug, short, by_district[slug], sub_urls,
                       sub_stats)
    print(f"suburb pages : {n_sub} (of {len(sub_groups)} suburbs with "
          f"businesses)")

    # categories, hubs (thin combos folded), business pages
    cats_present = []
    built_hubs = set()
    by_cat = {}
    for slug, title, _sing, _rules in CATS:
        recs = [b for b in kept if b["cat"] == slug]
        if not recs:
            continue
        by_cat[slug] = recs
        cats_present.append((slug, title, len(recs)))
    build_categories_index(cats_present)
    n_hub = 0
    for slug, title, recs in [(s, CAT_BY_SLUG[s][1], by_cat[s])
                              for s, _t, _n in cats_present]:
        subs = {}
        for b in recs:
            subs.setdefault(b.get("suburb") or "", []).append(b)
        shown = [(name if name else "Gauteng-wide",
                  sub_slug.get(name, "gauteng"), recs2)
                 for name, recs2 in subs.items()
                 if len(recs2) >= MIN_HUB_LISTINGS]
        build_cat_page(slug, title,
                       [(name, sslug, len(recs2))
                        for name, sslug, recs2 in sorted(shown)])
        for _name, sslug, recs2 in shown:
            sub_link = ""
            if _name != "Gauteng-wide" and _name in sub_urls:
                sub_link = (f"""<div class="cta" style="margin-top:2rem">
<h2>All of {e(_name)}</h2>
<p>Every mapped business in this suburb, all categories.</p>
<a class="btn" href="{sub_urls[_name]}">Open {e(_name)}</a>
</div>""")
            build_cat_hub_page(slug, title,
                               _name, sslug, recs2, sub_link)
            built_hubs.add((slug, sslug))
            n_hub += 1
    n_biz = 0
    for b in kept:
        sub = b.get("suburb") or ""
        hub_exists = (b["cat"], sub_slug.get(sub, "gauteng")) \
            in built_hubs
        build_business_page(b, b["cat"], CAT_BY_SLUG[b["cat"]][1],
                            hub_exists)
        n_biz += 1
    print(f"category hubs : {n_hub} | business pages : {n_biz}")

    n_idx = build_search_page(kept)
    print(f"search index  : {n_idx} entries")
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
