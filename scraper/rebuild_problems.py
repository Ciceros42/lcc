"""
rebuild_problems.py
===================
Rebuilds window.PROBLEMS in problems.js with:
  - boulder_url: link to the specific boulder HTML page each problem lives on
  - topo_img / topo_imgs: real CDN URLs from scraped_data.json (where available)
  - subarea_url: corrected to match the real subarea page (not generate_site artifact)

Usage: py rebuild_problems.py
"""

import json, re
from pathlib import Path
from collections import defaultdict

ROOT         = Path(__file__).parent.parent
BOULDERS_DIR = ROOT / "boulders"
DATA_JS      = ROOT / "data" / "problems.js"
SCRAPER_DIR  = Path(__file__).parent
SCRAPED_DATA = SCRAPER_DIR / "scraped_data.json"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── Step 1: Parse boulder pages → problem_id → boulder info ──────────────────

print("Step 1: Parsing boulder pages for problem anchors …")
problem_to_boulder: dict[str, dict] = {}   # problem_id → {boulder_url, subarea_url, area_url}

for path in BOULDERS_DIR.glob("*.html"):
    text = path.read_text(encoding="utf-8", errors="ignore")
    boulder_url = f"boulders/{path.name}"

    # Extract subarea URL
    sam = re.search(r'href=["\'][./]*subareas/([^"\']+)\.html', text)
    subarea_url = f"subareas/{sam.group(1)}.html" if sam else ""

    # Extract area URL
    am = re.search(r'href=["\'][./]*areas/([^"\']+)\.html', text)
    area_url = f"areas/{am.group(1)}.html" if am else ""

    # Extract all problem IDs in this boulder page
    for pid in re.findall(r'id=["\']+(problem-[^"\']+)["\']', text):
        if pid not in problem_to_boulder:
            problem_to_boulder[pid] = {
                "boulder_url":  boulder_url,
                "subarea_url":  subarea_url,
                "area_url":     area_url,
            }

print(f"  Mapped {len(problem_to_boulder)} problems to boulder pages")


# ── Step 2: Load topo data from scraped_data.json ─────────────────────────────

print("\nStep 2: Loading topo data from scraped_data.json …")
scraped_by_name: dict[str, dict] = {}   # slug(name) → {topo_img, topo_imgs}

if SCRAPED_DATA.exists():
    raw = json.loads(SCRAPED_DATA.read_text(encoding="utf-8"))
    for p in raw.get("problems", []):
        name_slug = slugify(p.get("name", ""))
        topo_img  = p.get("topo_img", "placeholder.svg")
        topo_imgs = p.get("topo_imgs", [])
        if topo_img and "placeholder" not in topo_img:
            scraped_by_name[name_slug] = {
                "topo_img":  topo_img,
                "topo_imgs": topo_imgs,
            }
    print(f"  Loaded topo data for {len(scraped_by_name)} problems")
else:
    print("  WARNING: scraped_data.json not found")


# ── Step 3: Load current PROBLEMS and patch ───────────────────────────────────

print("\nStep 3: Patching PROBLEMS in problems.js …")
js_text = DATA_JS.read_text(encoding="utf-8")

m = re.search(r'window\.PROBLEMS\s*=\s*(\[[\s\S]*?\]);\s*\n', js_text)
if not m:
    print("ERROR: window.PROBLEMS not found in problems.js")
    exit(1)

problems = json.loads(m.group(1))
print(f"  Loaded {len(problems)} problems")

patched_boulder = 0
patched_topo    = 0
patched_subarea = 0

for p in problems:
    pid        = p.get("id", "")
    name_slug  = slugify(p.get("name", ""))

    # Patch boulder_url
    boulder_info = problem_to_boulder.get(pid)
    if boulder_info:
        p["boulder_url"] = boulder_info["boulder_url"]
        # Also fix subarea_url if the boulder has a better one
        if boulder_info["subarea_url"]:
            p["subarea_url"] = boulder_info["subarea_url"]
            patched_subarea += 1
        patched_boulder += 1

    # Patch topo_img / topo_imgs
    topo_info = scraped_by_name.get(name_slug)
    if topo_info:
        p["topo_img"]  = topo_info["topo_img"]
        p["topo_imgs"] = topo_info["topo_imgs"]
        patched_topo += 1
    elif "topo_img" not in p or p["topo_img"] == "placeholder.svg":
        p["topo_img"] = ""   # empty string is cleaner than "placeholder.svg"

print(f"  Patched boulder_url: {patched_boulder}")
print(f"  Patched topo_img:    {patched_topo}")
print(f"  Patched subarea_url: {patched_subarea}")


# ── Step 4: Write back ────────────────────────────────────────────────────────

print("\nStep 4: Writing updated problems.js …")

new_block = "window.PROBLEMS = [\n"
for i, p in enumerate(problems):
    comma = "," if i < len(problems) - 1 else ""
    new_block += "  " + json.dumps(p) + comma + "\n"
new_block += "];\n"

js_text = re.sub(r'window\.PROBLEMS\s*=\s*\[[\s\S]*?\];\s*\n', lambda _: new_block, js_text)
DATA_JS.write_text(js_text, encoding="utf-8")
print(f"  Done. problems.js updated.")

# Summary
unmatched = sum(1 for p in problems if not p.get("boulder_url"))
print(f"\nSummary:")
print(f"  {patched_boulder}/{len(problems)} problems linked to a boulder page")
print(f"  {patched_topo}/{len(problems)} problems have real topo URLs")
print(f"  {unmatched} problems have no boulder_url (not in boulder pages)")
