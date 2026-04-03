"""
restore_site.py
===============
Restores the site after generate_site.py flattened the hierarchy.

What broke:
  - problems.js lost window.BOULDERS and window.SUBAREAS
  - Area pages were regenerated showing only 1 subarea each
  - Subarea pages matching area names (e.g. 5-mile-5-mile.html) were overwritten

How this fixes it:
  1. Parses surviving subareas/*.html to extract Kaya subarea IDs
  2. Parses all boulders/*.html to extract boulder data (name, GPS, climb count, etc.)
  3. Rebuilds window.BOULDERS in problems.js
  4. Rebuilds window.SUBAREAS in problems.js (centroid of each subarea's boulders)
  5. Regenerates area pages to list correct subareas dynamically
  6. Restores overwritten subarea pages to the dynamic boulder-list template

Usage
-----
  cd scraper
  py restore_site.py
"""

import json, re
from pathlib import Path
from collections import defaultdict

SCRAPER_DIR  = Path(__file__).parent
ROOT         = SCRAPER_DIR.parent
SUBAREAS_DIR = ROOT / "subareas"
BOULDERS_DIR = ROOT / "boulders"
AREAS_DIR    = ROOT / "areas"
DATA_JS      = ROOT / "data" / "problems.js"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── Step 1: Parse subareas/*.html → subarea_slug: subarea_id ─────────────────

print("Step 1: Reading subarea IDs from subareas/*.html …")
subarea_id_by_slug: dict[str, str] = {}   # "5-mile-cheese-whiz" → "18912"
subarea_info: dict[str, dict] = {}        # subarea_id → {name, area_name, area_slug, url}

for path in SUBAREAS_DIR.glob("*.html"):
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r'var\s+subareaId\s*=\s*["\'](\d+)["\']', text)
    if not m:
        continue
    sa_id   = m.group(1)
    sa_slug = path.stem   # e.g. "5-mile-cheese-whiz"

    # Extract subarea name from <h1>
    nm = re.search(r'<h1[^>]*>(.*?)</h1>', text)
    sa_name = nm.group(1).strip() if nm else sa_slug

    # Extract area name + slug from breadcrumb link to ../areas/
    am = re.search(r'href=["\.]*/areas/([^"\']+)\.html["\'][^>]*>([^<]+)<', text)
    area_slug = am.group(1) if am else ""
    area_name = am.group(2).strip() if am else ""

    subarea_id_by_slug[sa_slug] = sa_id
    subarea_info[sa_id] = {
        "id":        sa_id,
        "name":      sa_name,
        "area_name": area_name,
        "area_slug": area_slug,
        "url":       f"subareas/{sa_slug}.html",
    }

print(f"  Found {len(subarea_id_by_slug)} subarea IDs")


# ── Step 2: Parse boulders/*.html → BOULDERS list ────────────────────────────

print("\nStep 2: Parsing boulder pages …")
boulders: list[dict] = []

for path in BOULDERS_DIR.glob("*.html"):
    text = path.read_text(encoding="utf-8", errors="ignore")

    # Boulder name = last breadcrumb <span class="current">
    nm = re.findall(r'<span class=["\']current["\']>([^<]+)</span>', text)
    boulder_name = nm[-1].strip() if nm else path.stem

    # GPS from <span class="stat-value coords">lat, lng</span>
    gm = re.search(r'class=["\']stat-value coords["\']>([\d\-\.]+),\s*([\d\-\.]+)<', text)
    lat = gm.group(1) if gm else ""
    lng = gm.group(2) if gm else ""

    # Climb count from label "Climbs" followed by stat-value
    cm = re.search(r'<span class=["\']stat-label["\']>Climbs</span>'
                   r'\s*<span class=["\']stat-value["\']>(\d+)</span>', text)
    climb_count = int(cm.group(1)) if cm else 0

    # Subarea: second <a href="../subareas/..."> in breadcrumb
    sam = re.search(r'href=["\'][./]*subareas/([^"\']+)\.html["\'][^>]*>([^<]+)<', text)
    sa_slug = sam.group(1) if sam else ""
    sa_name = sam.group(2).strip() if sam else ""

    # Area: <a href="../areas/...">
    am = re.search(r'href=["\'][./]*areas/([^"\']+)\.html["\'][^>]*>([^<]+)<', text)
    area_slug = am.group(1) if am else ""
    area_name = am.group(2).strip() if am else ""

    # Subarea ID lookup
    sa_id = subarea_id_by_slug.get(sa_slug, "")

    boulder_url = f"boulders/{path.name}"

    boulders.append({
        "name":         boulder_name,
        "latitude":     lat,
        "longitude":    lng,
        "climb_count":  climb_count,
        "subarea_id":   sa_id,
        "subarea_name": sa_name,
        "subarea_url":  f"subareas/{sa_slug}.html",
        "area_name":    area_name,
        "area_url":     f"areas/{area_slug}.html",
        "url":          boulder_url,
    })

print(f"  Parsed {len(boulders)} boulders")
with_id  = sum(1 for b in boulders if b["subarea_id"])
with_gps = sum(1 for b in boulders if b["latitude"])
print(f"  With subarea ID: {with_id}")
print(f"  With GPS: {with_gps}")


# ── Step 3: Build window.SUBAREAS from subarea_info + boulder centroids ───────

print("\nStep 3: Building SUBAREAS …")

# Compute centroid per subarea from its boulders
sa_coords: dict[str, list] = defaultdict(list)
for b in boulders:
    if b["subarea_id"] and b["latitude"] and b["longitude"]:
        sa_coords[b["subarea_id"]].append(
            (float(b["latitude"]), float(b["longitude"]))
        )

subareas_list = []
for sa_id, info in subarea_info.items():
    coords = sa_coords.get(sa_id, [])
    if coords:
        lat = sum(c[0] for c in coords) / len(coords)
        lng = sum(c[1] for c in coords) / len(coords)
    else:
        lat = lng = None
    boulder_count = sum(1 for b in boulders if b["subarea_id"] == sa_id)
    subareas_list.append({
        "id":           sa_id,
        "name":         info["name"],
        "area_name":    info["area_name"],
        "area_url":     f"areas/{info['area_slug']}.html",
        "url":          info["url"],
        "latitude":     str(lat) if lat else "",
        "longitude":    str(lng) if lng else "",
        "boulder_count": boulder_count,
    })

print(f"  Built {len(subareas_list)} subareas")


# ── Step 4: Append BOULDERS + SUBAREAS to problems.js ────────────────────────

print("\nStep 4: Updating problems.js …")

existing = DATA_JS.read_text(encoding="utf-8")

# Remove any old BOULDERS / SUBAREAS blocks
existing = re.sub(r"\n*window\.BOULDERS\s*=[\s\S]*?;\s*(?=\n|$)", "",
                  existing, flags=re.MULTILINE)
existing = re.sub(r"\n*window\.SUBAREAS\s*=[\s\S]*?;\s*(?=\n|$)", "",
                  existing, flags=re.MULTILINE)

boulders_js  = "\n\nwindow.BOULDERS = " + json.dumps(boulders, indent=2) + ";\n"
subareas_js  = "\nwindow.SUBAREAS = " + json.dumps(subareas_list, indent=2) + ";\n"

DATA_JS.write_text(existing.rstrip() + boulders_js + subareas_js, encoding="utf-8")
print(f"  Written {len(boulders)} boulders + {len(subareas_list)} subareas to problems.js")


# ── Step 5: Restore area pages ────────────────────────────────────────────────

print("\nStep 5: Restoring area pages …")

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

# Get unique areas from subareas_list
area_names = {}
for s in subareas_list:
    an = s["area_name"]
    if an:
        area_names[slug(an)] = an

restored_areas = 0
for area_slug, area_name in area_names.items():
    html = AREA_TEMPLATE.format(
        area_name    = area_name,
        area_name_js = json.dumps(area_name),
    )
    out = AREAS_DIR / f"{area_slug}.html"
    out.write_text(html, encoding="utf-8")
    restored_areas += 1

print(f"  Restored {restored_areas} area pages")


# ── Step 6: Restore overwritten subarea pages ─────────────────────────────────

print("\nStep 6: Restoring overwritten subarea pages …")

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
  var subareaId = {subarea_id_js};
  var list     = document.getElementById('boulder-list');
  var subtitle = document.getElementById('sub-subtitle');
  var boulders = (window.BOULDERS || []).filter(function(b) {{ return b.subarea_id === subareaId; }});

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

# A subarea page needs restoration if it doesn't contain 'var subareaId'
# (generate_site.py wrote a static version without it)
restored_subs = 0
for path in SUBAREAS_DIR.glob("*.html"):
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "subareaId" in text:
        continue   # original dynamic template — fine

    # This was overwritten. Find matching subarea info.
    sa_slug = path.stem
    sa_id   = subarea_id_by_slug.get(sa_slug)

    # Try to derive area/subarea names from slug (e.g. "5-mile-5-mile")
    # Look it up from subarea_info if we have it via a different slug
    if not sa_id:
        # slug like "5-mile-5-mile": area slug = "5-mile", subarea slug = "5-mile"
        # check if the subarea info exists under a different subarea slug
        # (some areas are their own subarea, e.g. Blind Spot)
        parts = sa_slug.rsplit("-", 1)
        if len(parts) == 2:
            # Try the parent area's subarea of the same name
            for sid, info in subarea_info.items():
                if slug(info["name"]) == parts[-1] and slug(info["area_name"]) == parts[0]:
                    sa_id = sid
                    break

    if not sa_id:
        print(f"  SKIP {path.name} — can't find subarea ID")
        continue

    info = subarea_info.get(sa_id, {})
    html = SUBAREA_TEMPLATE.format(
        subarea_name   = info.get("name", sa_slug),
        area_name      = info.get("area_name", ""),
        area_slug      = info.get("area_slug", ""),
        subarea_id_js  = json.dumps(sa_id),
    )
    path.write_text(html, encoding="utf-8")
    restored_subs += 1
    print(f"  Restored subareas/{path.name}")

print(f"\n  Restored {restored_subs} subarea pages")

print("\n" + "=" * 55)
print("Done!")
print(f"  {len(boulders)} boulders in window.BOULDERS")
print(f"  {len(subareas_list)} subareas in window.SUBAREAS")
print(f"  {restored_areas} area pages rebuilt")
print(f"  {restored_subs} subarea pages restored")
