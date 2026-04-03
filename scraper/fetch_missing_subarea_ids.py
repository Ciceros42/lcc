"""
fetch_missing_subarea_ids.py
============================
Fetches Kaya subareaIds for the subarea pages that were overwritten
by generate_site.py (single-subarea areas where subarea = area name).

Writes missing_subarea_ids.json: {sa_slug: sa_id}
Then patches restore_site.py output: updates boulders' subarea_id and
restores the overwritten subarea pages.

Usage: py fetch_missing_subarea_ids.py
"""

import json, re, time, os
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()
SCRAPER_DIR   = Path(__file__).parent
ROOT          = SCRAPER_DIR.parent
TOKEN_FILE    = SCRAPER_DIR / "auth_token.txt"
GRAPHQL_URL   = "https://kaya-beta.kayaclimb.com/graphql"
DATA_JS       = ROOT / "data" / "problems.js"
SUBAREAS_DIR  = ROOT / "subareas"
BOULDERS_DIR  = ROOT / "boulders"
OUTPUT_FILE   = SCRAPER_DIR / "missing_subarea_ids.json"


# ── Auth ──────────────────────────────────────────────────────────────────────

def load_token() -> str:
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text(encoding="utf-8")).get("headers", {}).get("authorization", "")
        except Exception:
            pass
    return ""


def base_headers(token: str) -> dict:
    return {
        "Content-Type":    "application/json",
        "Authorization":   token,
        "User-Agent":      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
        "Accept":          "application/json",
        "Origin":          "https://kaya-app.kayaclimb.com",
        "Referer":         "https://kaya-app.kayaclimb.com/",
    }


def gql(query: str, variables: dict, token: str) -> dict:
    r = requests.post(GRAPHQL_URL, json={"query": query, "variables": variables},
                      headers=base_headers(token), timeout=30)
    if r.status_code == 403:
        raise RuntimeError("Cloudflare 403 — IP blocked.")
    body = r.json()
    if r.status_code == 200 and "errors" not in body:
        return body.get("data", {})
    errs = body.get("errors", [])
    msg  = errs[0]["message"] if errs else r.text[:200]
    raise RuntimeError(f"GraphQL error: {msg}")


LOCATIONS_QUERY = """
query webLocationsForLocation($location_id: ID!, $offset: Int!, $count: Int!, $climb_type_id: ID) {
  webLocationsForLocation(location_id: $location_id, offset: $offset, count: $count, climb_type_id: $climb_type_id) {
    id
    slug
    name
    latitude
    longitude
    __typename
  }
}
"""

def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def fetch_children(area_id: str, token: str) -> list:
    results = []
    offset = 0
    while True:
        data = gql(LOCATIONS_QUERY, {"location_id": area_id, "offset": offset, "count": 50, "climb_type_id": "1"}, token)
        page = data.get("webLocationsForLocation") or []
        results.extend(page)
        if len(page) < 50:
            break
        offset += 50
        time.sleep(1.0)
    return results


# ── Identify missing subareas ─────────────────────────────────────────────────

# From boulders, find which subarea slugs are referenced
boulder_sa_refs: dict[str, int] = {}
for p in BOULDERS_DIR.glob("*.html"):
    text = p.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r'href=["\'][./]*subareas/([^"\']+)\.html', text)
    if m:
        sa = m.group(1)
        boulder_sa_refs[sa] = boulder_sa_refs.get(sa, 0) + 1

# Find subarea pages without ID that have boulders
missing: dict[str, dict] = {}  # sa_slug -> {area_slug, area_name}
for p in SUBAREAS_DIR.glob("*.html"):
    text = p.read_text(encoding="utf-8", errors="ignore")
    if re.search(r'subareaId', text):
        continue
    sa_slug = p.stem
    if boulder_sa_refs.get(sa_slug, 0) == 0:
        continue  # no boulders reference it — probably artifact
    # Extract area info from page
    am = re.search(r'href=["\'][./]*areas/([^"\']+)\.html["\'][^>]*>([^<]+)<', text)
    if am:
        missing[sa_slug] = {"area_slug": am.group(1), "area_name": am.group(2).strip()}

print(f"Found {len(missing)} overwritten subarea pages with boulders:")
for slug, info in missing.items():
    print(f"  {slug} (area: {info['area_name']}, boulders: {boulder_sa_refs[slug]})")


# ── Area ID lookup ────────────────────────────────────────────────────────────

area_metas = json.loads(
    Path(SCRAPER_DIR / "checkpoint_climbs.json").read_text(encoding="utf-8")
).get("area_metas", [])
area_id_by_slug = {slugify(m["name"]): m["id"] for m in area_metas}


# ── Fetch subarea IDs from Kaya ───────────────────────────────────────────────

token = load_token()
if not token:
    print("ERROR: No token found. Run any probe script first to login.")
    exit(1)

# Verify token
try:
    result = gql("{ currentUser { id } }", {}, token)
    print(f"\nToken valid. User id: {result.get('currentUser', {}).get('id')}\n")
except RuntimeError as e:
    print(f"Token invalid: {e}")
    print("Run scrape_topos.py or another script to refresh the token, then retry.")
    exit(1)

found: dict[str, str] = {}  # sa_slug -> sa_id

# Load existing results if any
if OUTPUT_FILE.exists():
    found = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    print(f"Loaded {len(found)} already-found IDs from {OUTPUT_FILE.name}")

for sa_slug, info in missing.items():
    if sa_slug in found:
        print(f"  {sa_slug} — already have ID {found[sa_slug]}, skipping")
        continue

    area_slug = info["area_slug"]
    area_name = info["area_name"]
    area_id   = area_id_by_slug.get(area_slug)

    if not area_id:
        print(f"  {sa_slug} — no area ID for '{area_slug}', skipping")
        continue

    print(f"  Fetching children of '{area_name}' (id={area_id}) …", end=" ", flush=True)
    try:
        children = fetch_children(area_id, token)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        break

    print(f"{len(children)} children found")
    for child in children:
        child_slug = slugify(child["name"])
        combined_slug = f"{area_slug}-{child_slug}"
        print(f"    {combined_slug}: id={child['id']}")
        if combined_slug == sa_slug:
            found[sa_slug] = child["id"]
            print(f"    *** MATCHED {sa_slug} → {child['id']} ***")

    if sa_slug not in found:
        print(f"    ! No match found for {sa_slug}")

    OUTPUT_FILE.write_text(json.dumps(found, indent=2), encoding="utf-8")
    time.sleep(1.5)

print(f"\nFound {len(found)}/{len(missing)} IDs. Saved to {OUTPUT_FILE.name}")


# ── Patch problems.js: update boulder subarea_ids ─────────────────────────────

print("\nPatching problems.js …")
js_text = DATA_JS.read_text(encoding="utf-8")

# Extract BOULDERS array
m = re.search(r'window\.BOULDERS\s*=\s*(\[[\s\S]*?\]);\s*\n', js_text)
if not m:
    print("ERROR: window.BOULDERS not found in problems.js")
    exit(1)

boulders = json.loads(m.group(1))
patched = 0

for b in boulders:
    if b.get("subarea_id"):
        continue
    # Find which sa_slug this boulder's subarea_url matches
    su = b.get("subarea_url", "")  # e.g. "subareas/east-gate-east-gate.html"
    slug_match = re.search(r"subareas/([^.]+)\.html", su)
    if not slug_match:
        continue
    sa_slug = slug_match.group(1)
    if sa_slug in found:
        b["subarea_id"] = found[sa_slug]
        patched += 1

print(f"  Patched {patched} boulders with subarea IDs")

# Write back
new_boulders_block = "\n\nwindow.BOULDERS = " + json.dumps(boulders, indent=2) + ";\n"
js_text = re.sub(r'\n*window\.BOULDERS\s*=\s*\[[\s\S]*?\];\s*\n?', new_boulders_block, js_text)
DATA_JS.write_text(js_text, encoding="utf-8")
print(f"  Wrote updated problems.js")


# ── Restore overwritten subarea pages ─────────────────────────────────────────

print("\nRestoring subarea pages …")

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

restored = 0
for sa_slug, sa_id in found.items():
    info = missing.get(sa_slug, {})
    area_slug = info.get("area_slug", "")
    area_name = info.get("area_name", "")
    # Extract subarea name from the slug (remove area prefix)
    if sa_slug.startswith(area_slug + "-"):
        sa_name_slug = sa_slug[len(area_slug)+1:]
    else:
        sa_name_slug = sa_slug
    # Convert slug back to name (best effort: capitalize words)
    sa_name = " ".join(w.capitalize() for w in sa_name_slug.split("-"))
    # Use area name as subarea name if they match
    if slugify(area_name) == sa_name_slug:
        sa_name = area_name

    html = SUBAREA_TEMPLATE.format(
        subarea_name   = sa_name,
        area_name      = area_name,
        area_slug      = area_slug,
        subarea_id_js  = json.dumps(sa_id),
    )
    out = SUBAREAS_DIR / f"{sa_slug}.html"
    out.write_text(html, encoding="utf-8")
    restored += 1
    print(f"  Wrote subareas/{sa_slug}.html (id={sa_id})")

print(f"\nDone! Restored {restored} subarea pages, patched {patched} boulders.")
