"""
generate_site.py
================
Reads scraped_data.json (output of scrape_kaya.py) and regenerates:

  ../data/problems.js          — replaces mock data with real Kaya data
  ../subareas/<name>.html      — one page per sub-area with real problems
  ../areas/<name>.html         — area pages updated with real sub-areas

Usage
-----
  python generate_site.py

If the scraper found data but the auto-mapping is incomplete, you can edit
scraped_data.json by hand to correct area/sub-area assignments, then re-run.
"""

import json
import re
import textwrap
from pathlib import Path
from collections import defaultdict

SCRAPER_DIR = Path(__file__).parent
ROOT        = SCRAPER_DIR.parent
INPUT_FILE  = SCRAPER_DIR / "scraped_data.json"
TOPOS_DIR   = ROOT / "images" / "topos"

AREAS_DIR    = ROOT / "areas"
SUBAREAS_DIR = ROOT / "subareas"
DATA_DIR     = ROOT / "data"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def stars_html(n: int) -> str:
    return "".join(["★" if i < n else "☆" for i in range(3)])


def grade_num(label: str) -> int:
    m = re.search(r"(\d+)", str(label))
    return int(m.group(1)) if m else 0


# ── Load scraped data ─────────────────────────────────────────────────────────

if not INPUT_FILE.exists():
    print(f"ERROR: {INPUT_FILE} not found. Run scrape_kaya.py first.")
    exit(1)

raw = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
meta     = raw.get("meta", {})
areas    = raw.get("areas", [])
problems = raw.get("problems", [])

print(f"Loaded scraped data from {INPUT_FILE.name}")
print(f"  Areas:    {len(areas)}")
print(f"  Problems: {len(problems)}")

if not problems:
    print("\nWARNING: No problems found in scraped_data.json.")
    print("The scraper may need adjustment for Kaya's specific API response format.")
    print("Open scraped_data.json and inspect 'raw_responses' to find the problem data,")
    print("then update extract_problems_from_payload() in scrape_kaya.py and re-run.\n")
    exit(1)


# ── Normalize problems ────────────────────────────────────────────────────────

def normalize(p: dict, area_name: str, subarea_name: str) -> dict:
    def first(*keys):
        for k in keys:
            if k in p and p[k] is not None:
                return p[k]
        return None

    name      = first("name", "title", "problemName") or "Unknown"
    gl_raw    = first("grade", "vGrade", "v_grade", "gradeLabel", "difficulty") or ""
    gl        = str(gl_raw).strip()
    if gl and not gl.upper().startswith("V"):
        gl = f"V{gl}"
    gl = gl.upper()

    stars_raw = first("stars", "rating", "quality", "starRating") or 0
    try:
        stars = max(0, min(3, round(float(stars_raw))))
    except (TypeError, ValueError):
        stars = 0

    desc      = first("description", "beta", "notes", "text", "body") or ""
    topo_url  = first("topoImageUrl", "imageUrl", "image", "topo",
                      "thumbnailUrl", "photoUrl") or ""

    # Resolve topo image path
    topo_img = "placeholder.svg"
    if topo_url:
        ext = Path(topo_url).suffix or ".jpg"
        candidate = TOPOS_DIR / f"{slug(name)}{ext}"
        if candidate.exists():
            topo_img = candidate.name

    sa_slug = slug(f"{slug(area_name)}-{slug(subarea_name)}")

    return {
        "id":          f"problem-{slug(name)}",
        "name":        name,
        "grade":       grade_num(gl),
        "gradeLabel":  gl or "V?",
        "stars":       stars,
        "area":        area_name,
        "area_url":    f"areas/{slug(area_name)}.html",
        "subarea":     subarea_name,
        "subarea_url": f"subareas/{sa_slug}.html",
        "description": desc,
        "topo_img":    topo_img,
    }


# ── Group problems by area → sub-area ─────────────────────────────────────────
#
# Kaya data may already have area/subArea fields or may use a flat list.
# We try multiple field names and fall back to grouping under a single area.

grouped: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

for p in problems:
    area_name    = (
        p.get("areaName") or p.get("area") or p.get("locationName") or
        p.get("parentName") or "Little Cottonwood Canyon"
    )
    subarea_name = (
        p.get("subareaName") or p.get("subarea") or p.get("sectorName") or
        p.get("zoneName") or p.get("wallName") or "Main Area"
    )
    norm = normalize(p, area_name, subarea_name)
    grouped[area_name][subarea_name].append(norm)

print(f"\nGrouped into {len(grouped)} area(s):")
for aname, subareas in grouped.items():
    total = sum(len(ps) for ps in subareas.values())
    print(f"  {aname}: {len(subareas)} sub-area(s), {total} problems")
    for saname, ps in subareas.items():
        grades = [p["gradeLabel"] for p in ps if p["gradeLabel"] != "V?"]
        print(f"    {saname}: {len(ps)} problems  {', '.join(grades[:5])}{'…' if len(grades)>5 else ''}")


# ── Generate problems.js ──────────────────────────────────────────────────────

all_normalized = []
for aname, subareas in grouped.items():
    for saname, ps in subareas.items():
        all_normalized.extend(ps)

# Build area metadata lookup from scraped_data.json areas list
area_meta_lookup = {a["name"]: a for a in areas}

area_summaries = []
for aname, subareas in grouped.items():
    all_ps    = [p for ps in subareas.values() for p in ps]
    grades    = sorted([p["grade"] for p in all_ps])
    grade_min = f"V{grades[0]}"  if grades else "V?"
    grade_max = f"V{grades[-1]}" if grades else "V?"
    meta      = area_meta_lookup.get(aname, {})
    area_summaries.append({
        "id":           slug(aname),
        "name":         aname,
        "url":          f"areas/{slug(aname)}.html",
        "gradeRange":   f"{grade_min}–{grade_max}",
        "problemCount": len(all_ps),
        "subareas":     list(subareas.keys()),
        "latitude":     meta.get("latitude"),
        "longitude":    meta.get("longitude"),
        "description":  meta.get("description", ""),
    })

js_lines = ["window.AREAS = " + json.dumps(area_summaries, indent=2) + ";\n\n"]
js_lines.append("window.PROBLEMS = [\n")
for i, p in enumerate(all_normalized):
    comma = "," if i < len(all_normalized) - 1 else ""
    js_lines.append("  " + json.dumps({k: v for k, v in p.items()}) + comma + "\n")
js_lines.append("];\n")

(DATA_DIR / "problems.js").write_text("".join(js_lines), encoding="utf-8")
print(f"\nWrote: data/problems.js  ({len(all_normalized)} problems)")


# ── Generate sub-area pages ───────────────────────────────────────────────────

HEADER = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — LCC Bouldering</title>
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
  <p class="page-subtitle">{area_name}</p>
  <div class="subarea-stats">
    <div class="stat-item"><span class="stat-label">Problems</span><span class="stat-value">{problem_count}</span></div>
    <div class="stat-item"><span class="stat-label">Grade Range</span><span class="stat-value">{grade_range}</span></div>
    <div class="stat-item"><span class="stat-label">Rock Type</span><span class="stat-value">Granite</span></div>
  </div>"""

FOOTER = """</main>
<footer class="site-footer">
  LCC Bouldering &mdash; Little Cottonwood Canyon, Utah &mdash; Data sourced from
  <a href="https://kayaclimb.com" target="_blank">Kaya</a>
</footer>
<script src="../js/scroll-top.js"></script>
</body>
</html>"""

PROBLEM_BLOCK = """
  <article class="problem-entry" id="{problem_id}">
    <div class="problem-header">
      <h2 class="problem-name">{name}</h2>
      <span class="grade-badge">{grade}</span>
      <span class="stars">{stars}</span>
    </div>
    <div class="problem-topo">
      <img src="../images/topos/{topo_img}" alt="Topo: {name}">
      <span class="topo-label">{name} — topo</span>
    </div>
    <p class="problem-description">{description}</p>
  </article>"""

generated_subareas = set()

for aname, subareas in grouped.items():
    for saname, ps in subareas.items():
        sa_slug = slug(f"{slug(aname)}-{slug(saname)}")
        grades  = sorted([p["grade"] for p in ps])
        gr      = f"V{grades[0]}–V{grades[-1]}" if grades else "V?"

        html  = HEADER.format(
            title=f"{saname} — {aname}",
            area_slug=slug(aname),
            area_name=aname,
            subarea_name=saname,
            problem_count=len(ps),
            grade_range=gr,
        )

        sorted_ps = sorted(ps, key=lambda x: x["grade"])

        # Climb name list (TOC)
        html += '\n  <nav class="climb-toc">\n    <h2 class="toc-heading">Climbs</h2>\n    <ol class="toc-list">\n'
        for p in sorted_ps:
            html += (f'      <li><a href="#{p["id"]}" class="toc-item">'
                     f'<span class="toc-name">{p["name"]}</span>'
                     f'<span class="toc-grade">{p["gradeLabel"]}</span></a></li>\n')
        html += '    </ol>\n  </nav>\n  <h2 class="section-heading">Details</h2>'

        # Full problem entries
        for i, p in enumerate(sorted_ps):
            html += PROBLEM_BLOCK.format(
                problem_id  = p["id"],
                name        = p["name"],
                grade       = p["gradeLabel"],
                stars       = stars_html(p["stars"]),
                topo_img    = p["topo_img"],
                description = p["description"] or "No description available.",
            )
            if i < len(sorted_ps) - 1:
                html += '\n  <hr class="problem-divider">'

        html += "\n" + FOOTER

        out = SUBAREAS_DIR / f"{sa_slug}.html"
        out.write_text(html, encoding="utf-8")
        generated_subareas.add(sa_slug)
        print(f"  Wrote: subareas/{sa_slug}.html  ({len(ps)} problems)")


# ── Generate area pages ───────────────────────────────────────────────────────

AREA_HEADER = """<!DOCTYPE html>
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
  <p class="page-subtitle">{problem_count} problems &nbsp;&middot;&nbsp; {grade_range} &nbsp;&middot;&nbsp; {subarea_count} sub-areas</p>
  <h2 class="section-heading">Sub-Areas</h2>
  <div class="subarea-list">"""

SUBAREA_CARD = """
    <a class="subarea-card" href="../subareas/{sa_slug}.html">
      <div class="subarea-card-info">
        <div class="subarea-card-name">{sa_name}</div>
        <div class="subarea-card-meta">
          <span>{count} problems</span>
          <span>{grade_range}</span>
        </div>
      </div>
      <span class="subarea-card-arrow">&rsaquo;</span>
    </a>"""

AREA_FOOTER = """
  </div>
</main>
<footer class="site-footer">
  LCC Bouldering &mdash; Little Cottonwood Canyon, Utah &mdash; Data sourced from
  <a href="https://kayaclimb.com" target="_blank">Kaya</a>
</footer>
<script src="../js/scroll-top.js"></script>
</body>
</html>"""

for aname, subareas in grouped.items():
    all_ps   = [p for ps in subareas.values() for p in ps]
    grades   = sorted([p["grade"] for p in all_ps])
    gr       = f"V{grades[0]}–V{grades[-1]}" if grades else "V?"

    html = AREA_HEADER.format(
        area_name     = aname,
        problem_count = len(all_ps),
        grade_range   = gr,
        subarea_count = len(subareas),
    )

    for saname, ps in subareas.items():
        sa_slug = slug(f"{slug(aname)}-{slug(saname)}")
        sg      = sorted([p["grade"] for p in ps])
        sgr     = f"V{sg[0]}–V{sg[-1]}" if sg else "V?"
        html   += SUBAREA_CARD.format(
            sa_slug    = sa_slug,
            sa_name    = saname,
            count      = len(ps),
            grade_range= sgr,
        )

    html += AREA_FOOTER

    out = AREAS_DIR / f"{slug(aname)}.html"
    out.write_text(html, encoding="utf-8")
    print(f"  Wrote: areas/{slug(aname)}.html")

print("\nDone! Site files have been updated with real Kaya data.")
print("Open LCC_Database/index.html in your browser to review.")
