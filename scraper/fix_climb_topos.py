"""
fix_climb_topos.py
==================
Fixes boulder pages so each climb entry shows the CORRECT topo image
for that specific climb instead of the first boulder topo for every climb.

Data source: scraped_data.json has topo_img per climb (from Kaya API).
Limitation:  We don't yet have per-climb polyline points, so the route
             line overlay is removed from per-climb entries. The gallery
             at the top of each boulder page (which correctly shows all
             topos with all route lines) is left untouched.

Usage: py fix_climb_topos.py
"""

import json, re
from pathlib import Path

SCRAPER_DIR  = Path(__file__).parent
ROOT         = SCRAPER_DIR.parent
BOULDERS_DIR = ROOT / "boulders"
SCRAPED_DATA = SCRAPER_DIR / "scraped_data.json"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── Build name_slug → topo_img lookup from scraped_data.json ─────────────────

print("Loading topo data from scraped_data.json …")
topo_by_slug: dict[str, str] = {}   # slugified_name → first topo URL

raw = json.loads(SCRAPED_DATA.read_text(encoding="utf-8"))
for p in raw.get("problems", []):
    name = p.get("name", "")
    topo = p.get("topo_img", "")
    if topo and "placeholder" not in topo:
        topo_by_slug[slugify(name)] = topo

print(f"  {len(topo_by_slug)} climbs have topo URLs")


# ── Process each boulder page ─────────────────────────────────────────────────

TOPO_DIV_RE = re.compile(
    r'<div class="problem-topo">.*?</div>\s*</div>',
    re.DOTALL
)

# Also handles the single-wrapper case (no inner closing div)
TOPO_OUTER_RE = re.compile(
    r'\s*<div class="problem-topo">[\s\S]*?(?=<p class="problem-description"|</article>)',
)

boulder_files = list(BOULDERS_DIR.glob("*.html"))
print(f"\nProcessing {len(boulder_files)} boulder pages …")

updated_pages = 0
updated_climbs = 0
cleared_climbs = 0

for path in boulder_files:
    text = path.read_text(encoding="utf-8", errors="ignore")

    # Find all problem-entry articles
    new_text = text
    changed = False

    for article_match in re.finditer(
        r'(<article class="problem-entry" id="([^"]+)">)([\s\S]*?)(</article>)',
        text
    ):
        full      = article_match.group(0)
        open_tag  = article_match.group(1)
        pid       = article_match.group(2)          # e.g. "problem-big-mouth"
        body      = article_match.group(3)
        close_tag = article_match.group(4)

        # Derive climb name slug from problem id ("problem-big-mouth" → "big-mouth")
        name_slug = pid.replace("problem-", "", 1)
        topo_url  = topo_by_slug.get(name_slug, "")

        # Build replacement problem-topo block
        if topo_url:
            new_topo = (
                '\n    <div class="problem-topo">\n'
                f'      <img src="{topo_url}" alt="Topo for {name_slug.replace("-", " ").title()}" loading="lazy">\n'
                '    </div>'
            )
            updated_climbs += 1
        else:
            new_topo = ""   # no topo for this climb — remove section entirely
            cleared_climbs += 1

        # Replace existing problem-topo div in body
        new_body = re.sub(
            r'\s*<div class="problem-topo">[\s\S]*?</div>\s*</div>',
            new_topo,
            body,
            count=1,
        )

        if new_body != body:
            new_full = open_tag + new_body + close_tag
            new_text = new_text.replace(full, new_full, 1)
            changed = True

    if changed:
        path.write_text(new_text, encoding="utf-8")
        updated_pages += 1

print(f"\nDone.")
print(f"  Updated pages:  {updated_pages}")
print(f"  Climbs with correct topo: {updated_climbs}")
print(f"  Climbs with no topo (section removed): {cleared_climbs}")
print()
print("Note: route-line overlays removed from per-climb entries.")
print("To restore them, re-scrape wall_topo_shapes with 'points' field when API is available.")
