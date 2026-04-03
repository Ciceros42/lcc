"""
update_map_subareas.py
======================
Reads scraped_subareas.json and injects sub-area / boulder coordinates
into data/problems.js as window.SUBAREAS, so the map can show them.

Run after scrape_subareas.py.

Usage
-----
  python update_map_subareas.py
"""

import json, re
from pathlib import Path

SCRAPER_DIR = Path(__file__).parent
ROOT        = SCRAPER_DIR.parent
INPUT_FILE  = SCRAPER_DIR / "scraped_subareas.json"
DATA_DIR    = ROOT / "data"

def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

def run():
    if not INPUT_FILE.exists():
        print(f"ERROR: {INPUT_FILE} not found. Run scrape_subareas.py first.")
        return

    data      = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    subareas  = data.get("subareas", [])
    print(f"Loaded {len(subareas)} sub-areas from {INPUT_FILE.name}")

    # Build compact list for the map — only include entries with coordinates
    map_entries = []
    for s in subareas:
        lat = s.get("latitude")
        lng = s.get("longitude")
        if not lat or not lng:
            continue
        map_entries.append({
            "id":           s["id"],
            "name":         s["name"],
            "parent":       s.get("_parent_name", ""),
            "parent_id":    s.get("_parent_id", ""),
            "latitude":     lat,
            "longitude":    lng,
            "boulder_count": s.get("boulder_count") or s.get("climb_count") or 0,
            "url":          f"subareas/{slug(s.get('_parent_name','') + '-' + s['name'])}.html",
        })

    print(f"Sub-areas with coordinates: {len(map_entries)}")

    # Append window.SUBAREAS to problems.js
    problems_js = DATA_DIR / "problems.js"
    if not problems_js.exists():
        print(f"ERROR: {problems_js} not found. Run generate_site.py first.")
        return

    existing = problems_js.read_text(encoding="utf-8")

    # Remove any previous SUBAREAS block
    existing = re.sub(r"\n*window\.SUBAREAS\s*=[\s\S]*?;\s*$", "", existing, flags=re.MULTILINE)

    subareas_js = "\n\nwindow.SUBAREAS = " + json.dumps(map_entries, indent=2) + ";\n"
    problems_js.write_text(existing.rstrip() + subareas_js, encoding="utf-8")
    print(f"Wrote window.SUBAREAS ({len(map_entries)} entries) to data/problems.js")
    print("\nNext step: open index.html — sub-area markers will appear on the map.")

if __name__ == "__main__":
    run()
