"""
patch_missing_subareas.py
=========================
Fixes the remaining 16+ broken area pages and 20 missing subarea pages
WITHOUT needing Kaya API access.

Strategy: filter boulders by subarea_url (the HTML path) instead of by
subareaId. The BOULDERS data already contains subarea_url for every
boulder, so this works offline.

Also converts the remaining flat area pages to dynamic templates.

Usage: py patch_missing_subareas.py
"""

import json, re
from pathlib import Path
from collections import defaultdict

ROOT          = Path(__file__).parent.parent
SUBAREAS_DIR  = ROOT / "subareas"
BOULDERS_DIR  = ROOT / "boulders"
AREAS_DIR     = ROOT / "areas"
DATA_JS       = ROOT / "data" / "problems.js"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── Load BOULDERS from problems.js ────────────────────────────────────────────

js_text = DATA_JS.read_text(encoding="utf-8")
m = re.search(r'window\.BOULDERS\s*=\s*(\[[\s\S]*?\]);\s*\n', js_text)
if not m:
    print("ERROR: window.BOULDERS not found in problems.js")
    exit(1)
boulders = json.loads(m.group(1))
print(f"Loaded {len(boulders)} boulders from problems.js")


# ── Find subarea pages without ID that have boulders referencing them ─────────

# Map subarea_url -> list of boulders
boulder_by_sa_url: dict[str, list] = defaultdict(list)
for b in boulders:
    su = b.get("subarea_url", "")
    if su:
        boulder_by_sa_url[su].append(b)

# Find subarea pages needing repair
missing_pages: list[dict] = []
for p in SUBAREAS_DIR.glob("*.html"):
    text = p.read_text(encoding="utf-8", errors="ignore")
    if "subareaId" in text:
        continue   # already has ID — fine
    sa_slug = p.stem
    sa_url  = f"subareas/{sa_slug}.html"
    count   = len(boulder_by_sa_url.get(sa_url, []))
    if count == 0:
        continue   # no boulders — likely artifact

    # Get area info from page
    am = re.search(r'href=["\'][./]*areas/([^"\']+)\.html["\'][^>]*>([^<]+)<', text)
    area_slug = am.group(1) if am else ""
    area_name = am.group(2).strip() if am else ""

    missing_pages.append({
        "sa_slug":   sa_slug,
        "sa_url":    sa_url,
        "area_slug": area_slug,
        "area_name": area_name,
        "count":     count,
    })

print(f"\nFound {len(missing_pages)} subarea pages missing IDs but with boulders:")
for mp in missing_pages:
    print(f"  {mp['sa_slug']}: {mp['count']} boulders")


# ── Subarea page template (URL-based boulder filtering) ───────────────────────

SUBAREA_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subarea_name} — {area_name} — LCC Bouldering</title>
  <link rel="stylesheet" href="../css/styles.css">
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <a class="site-logo" href="../index.html">LCC <span>Bouldering</span></a>
    <nav class="site-nav">
      <a href="../index.html">Areas</a>
      <a href="../index.html#search-section">Search</a>
    </nav>
  </div>
</header>
<main class="page-wrap">
  <nav class="breadcrumb">
    <a href="../index.html">Little Cottonwood Canyon</a>
    <span class="sep">/</span>
    <a href="../areas/{area_slug}.html">{area_name}</a>
    <span class="sep">/</span>
    <span class="current">{subarea_name}</span>
  </nav>
  <h1 class="page-title">{subarea_name}</h1>
  <p class="page-subtitle" id="sub-subtitle"></p>
  <h2 class="section-heading">Boulders</h2>
  <div class="boulder-list" id="boulder-list">
    <p class="loading-text">Loading…</p>
  </div>
</main>
<footer class="site-footer">
  LCC Bouldering &mdash; Little Cottonwood Canyon, Utah &mdash; Data sourced from
  <a href="https://kayaclimb.com" target="_blank">Kaya</a>
</footer>
<script src="../data/problems.js"></script>
<script>
(function() {{
  var saUrl    = {sa_url_js};
  var list     = document.getElementById('boulder-list');
  var subtitle = document.getElementById('sub-subtitle');
  var boulders = (window.BOULDERS || []).filter(function(b) {{ return b.subarea_url === saUrl; }});

  if (subtitle) {{
    var total = boulders.reduce(function(s, b) {{ return s + (b.climb_count || 0); }}, 0);
    subtitle.textContent = boulders.length + ' boulder' + (boulders.length !== 1 ? 's' : '')
      + ' · ' + total + ' climb' + (total !== 1 ? 's' : '');
  }}

  if (!boulders.length) {{
    list.innerHTML = '<p class="no-results">No boulders found.</p>';
    return;
  }}

  list.innerHTML = boulders.map(function(b) {{
    var locStr = (b.latitude && b.longitude)
      ? '<span class="boulder-coords">' + parseFloat(b.latitude).toFixed(5)
        + ', ' + parseFloat(b.longitude).toFixed(5) + '</span>'
      : '';
    var link  = b.url ? '../' + b.url : null;
    var inner = '<div class="boulder-card-info">'
      + '<div class="boulder-card-name">' + b.name + '</div>'
      + '<div class="boulder-card-meta">'
      +   '<span>' + (b.climb_count || 0) + ' climb' + (b.climb_count !== 1 ? 's' : '') + '</span>'
      +   locStr
      + '</div></div>'
      + (link ? '<span class="subarea-card-arrow">›</span>' : '');
    return link
      ? '<a class="boulder-card" href="' + link + '">' + inner + '</a>'
      : '<div class="boulder-card">' + inner + '</div>';
  }}).join('');
}})();
</script>
<script src="../js/scroll-top.js"></script>
</body>
</html>"""

restored_subs = 0
for mp in missing_pages:
    sa_slug   = mp["sa_slug"]
    sa_url    = mp["sa_url"]
    area_slug = mp["area_slug"]
    area_name = mp["area_name"]

    # Derive subarea name from slug (strip area prefix)
    if sa_slug.startswith(area_slug + "-"):
        sa_name_slug = sa_slug[len(area_slug)+1:]
    else:
        sa_name_slug = sa_slug
    # Use area name if subarea slug equals area slug
    if slugify(area_name) == sa_name_slug:
        sa_name = area_name
    else:
        sa_name = " ".join(w.capitalize() for w in sa_name_slug.split("-"))

    html = SUBAREA_TEMPLATE.format(
        subarea_name = sa_name,
        area_name    = area_name,
        area_slug    = area_slug,
        sa_url_js    = json.dumps(sa_url),
    )
    out = SUBAREAS_DIR / f"{sa_slug}.html"
    out.write_text(html, encoding="utf-8")
    restored_subs += 1
    print(f"  Wrote subareas/{sa_slug}.html ({mp['count']} boulders)")

print(f"\nRestored {restored_subs} subarea pages")


# ── Also fix SUBAREAS in problems.js to include these missing entries ─────────
# Compute centroids for missing subareas from their boulders

m2 = re.search(r'window\.SUBAREAS\s*=\s*(\[[\s\S]*?\]);\s*\n?', js_text)
subareas_list = json.loads(m2.group(1)) if m2 else []

existing_sa_urls = {s["url"] for s in subareas_list}

added = 0
for mp in missing_pages:
    if mp["sa_url"] in existing_sa_urls:
        continue
    bvs = boulder_by_sa_url.get(mp["sa_url"], [])
    coords = [(float(b["latitude"]), float(b["longitude"]))
              for b in bvs if b.get("latitude") and b.get("longitude")]
    lat = sum(c[0] for c in coords) / len(coords) if coords else None
    lng = sum(c[1] for c in coords) / len(coords) if coords else None
    total_climbs = sum(b.get("climb_count", 0) for b in bvs)

    sa_slug = mp["sa_slug"]
    if sa_slug.startswith(mp["area_slug"] + "-"):
        sa_name_slug = sa_slug[len(mp["area_slug"])+1:]
    else:
        sa_name_slug = sa_slug
    if slugify(mp["area_name"]) == sa_name_slug:
        sa_name = mp["area_name"]
    else:
        sa_name = " ".join(w.capitalize() for w in sa_name_slug.split("-"))

    subareas_list.append({
        "id":           "",    # no Kaya ID yet
        "name":         sa_name,
        "area_name":    mp["area_name"],
        "area_url":     f"areas/{mp['area_slug']}.html",
        "url":          mp["sa_url"],
        "latitude":     str(lat) if lat else "",
        "longitude":    str(lng) if lng else "",
        "boulder_count": len(bvs),
    })
    existing_sa_urls.add(mp["sa_url"])
    added += 1

print(f"\nAdded {added} entries to SUBAREAS list")

# Write updated SUBAREAS to problems.js
new_subs_block = "\nwindow.SUBAREAS = " + json.dumps(subareas_list, indent=2) + ";\n"
js_text = re.sub(r'\n*window\.SUBAREAS\s*=\s*\[[\s\S]*?\];\s*\n?', new_subs_block, js_text)
DATA_JS.write_text(js_text, encoding="utf-8")
print(f"Updated problems.js ({len(subareas_list)} total subareas)")


# ── Convert remaining flat area pages to dynamic templates ────────────────────

AREA_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{area_name} — LCC Bouldering</title>
  <link rel="stylesheet" href="../css/styles.css">
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <a class="site-logo" href="../index.html">LCC <span>Bouldering</span></a>
    <nav class="site-nav">
      <a href="../index.html">Areas</a>
      <a href="../index.html#search-section">Search</a>
    </nav>
  </div>
</header>
<main class="page-wrap">
  <nav class="breadcrumb">
    <a href="../index.html">Little Cottonwood Canyon</a>
    <span class="sep">/</span>
    <span class="current">{area_name}</span>
  </nav>
  <h1 class="page-title">{area_name}</h1>
  <p class="page-subtitle" id="area-subtitle"></p>
  <h2 class="section-heading">Sub-Areas</h2>
  <div class="subarea-list" id="subarea-list">
    <p class="loading-text">Loading…</p>
  </div>
</main>
<footer class="site-footer">
  LCC Bouldering &mdash; Little Cottonwood Canyon, Utah &mdash; Data sourced from
  <a href="https://kayaclimb.com" target="_blank">Kaya</a>
</footer>
<script src="../data/problems.js"></script>
<script>
(function() {{
  var areaName = {area_name_js};
  var areaUrl  = {area_url_js};
  var list     = document.getElementById('subarea-list');
  var subtitle = document.getElementById('area-subtitle');
  var subs = (window.SUBAREAS || []).filter(function(s) {{ return s.area_name === areaName; }});

  if (subtitle) {{
    var total = subs.reduce(function(n, s) {{ return n + (s.boulder_count || 0); }}, 0);
    subtitle.textContent = subs.length + ' sub-area' + (subs.length !== 1 ? 's' : '')
      + ' · ' + total + ' boulder' + (total !== 1 ? 's' : '');
  }}

  if (!subs.length) {{
    list.innerHTML = '<p class="no-results">No sub-areas found.</p>';
    return;
  }}

  list.innerHTML = subs.map(function(s) {{
    return '<a class="subarea-card" href="../' + s.url + '">'
      + '<div class="subarea-card-info">'
      + '<div class="subarea-card-name">' + s.name + '</div>'
      + '<div class="subarea-card-meta"><span>' + (s.boulder_count || 0)
      + ' boulder' + (s.boulder_count !== 1 ? 's' : '') + '</span></div>'
      + '</div>'
      + '<span class="subarea-card-arrow">›</span>'
      + '</a>';
  }}).join('');
}})();
</script>
<script src="../js/scroll-top.js"></script>
</body>
</html>"""

converted_areas = 0
for p in AREAS_DIR.glob("*.html"):
    text = p.read_text(encoding="utf-8", errors="ignore")
    if "window.SUBAREAS" in text:
        continue   # already dynamic

    # Extract area name from <h1>
    nm = re.search(r'<h1[^>]*>(.*?)</h1>', text)
    area_name = nm.group(1).strip() if nm else p.stem
    area_slug = p.stem
    area_url  = f"areas/{area_slug}.html"

    html = AREA_TEMPLATE.format(
        area_name    = area_name,
        area_name_js = json.dumps(area_name),
        area_url_js  = json.dumps(area_url),
    )
    p.write_text(html, encoding="utf-8")
    converted_areas += 1
    print(f"  Converted areas/{p.name}")

print(f"\nConverted {converted_areas} flat area pages to dynamic templates")
print("\nAll done!")
