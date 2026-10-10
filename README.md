# Gauteng Index

Parent directory of the [Sandton Index](https://skywalkingzulu1.github.io/sandton-index/):
every suburb-level place OpenStreetMap maps inside Gauteng, grouped by
district. Sandton is covered in depth on the child site.

## Build

```bash
python scripts/build.py   # generate site/ (includes verify gate)
```

`data/gauteng_suburbs.json` (1,242 places, harvested live from OSM) is the
only input. Suburbs are listed on district pages; no suburb gets its own
page. One mapped place resolves outside Gauteng and is kept in the data
file for audit, with no site page.

No Search Console token is configured yet -- add one and the generator can
emit the verification tag + file like the Sandton Index does.

## Pages

| URL | Contents |
|---|---|
| `/` | Hero, stats, district cards, child-site CTA |
| `/districts/` | All five districts |
| `/districts/{district}/` | Filterable suburb list + child-site panel |

Output: `site/` (7 pages) served from the `gh-pages` branch.
