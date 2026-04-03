"""
parse_mitmproxy.py
==================
Reads the HAR file exported from mitmweb and extracts all Kaya GraphQL
responses, then builds scraped_data.json and regenerates the site.

Usage
-----
  1. Export traffic from mitmweb as HAR → save to scraper/kaya_traffic.har
  2. python parse_mitmproxy.py
  3. python generate_site.py
"""

import json
import re
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from collections import defaultdict

SCRAPER_DIR = Path(__file__).parent
ROOT        = SCRAPER_DIR.parent
HAR_FILE    = SCRAPER_DIR / "kaya_traffic.har"
OUTPUT_FILE = SCRAPER_DIR / "scraped_data.json"
TOPOS_DIR   = ROOT / "images" / "topos"

GRAPHQL_HOST = "kaya-beta.kayaclimb.com"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def download_image(url: str, dest: Path) -> bool:
    try:
        r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(r, timeout=15) as resp:
            dest.write_bytes(resp.read())
        return True
    except Exception:
        return False


# ── Parse HAR ────────────────────────────────────────────────────────────────

def load_har(path: Path) -> list[dict]:
    """Return list of {operation, variables, response_data} for Kaya GQL calls."""
    if not path.exists():
        print(f"ERROR: {path} not found.")
        print("Export traffic from mitmweb: File → Export → Export as HAR")
        return []

    har = json.loads(path.read_text(encoding="utf-8"))
    entries = har.get("log", {}).get("entries", [])
    print(f"HAR contains {len(entries)} total requests")

    gql_entries = []
    for entry in entries:
        req = entry.get("request", {})
        url = req.get("url", "")

        if GRAPHQL_HOST not in url:
            continue

        # Parse request body
        op_name  = ""
        variables = {}
        try:
            body_text = req.get("postData", {}).get("text", "")
            if body_text:
                body = json.loads(body_text)
                op_name   = body.get("operationName", "")
                variables = body.get("variables", {})
        except Exception:
            pass

        # Parse response body
        resp_data = None
        try:
            resp_content = entry.get("response", {}).get("content", {})
            resp_text    = resp_content.get("text", "")
            if resp_text:
                parsed = json.loads(resp_text)
                resp_data = parsed.get("data")
        except Exception:
            pass

        if resp_data:
            gql_entries.append({
                "operation": op_name,
                "variables": variables,
                "data":      resp_data,
            })
            print(f"  [GQL ✓] {op_name or '(unnamed)'}")

    print(f"\n{len(gql_entries)} GraphQL responses with data captured")
    return gql_entries


# ── Extract problems recursively ──────────────────────────────────────────────

def extract_problems(node, area="", subarea="") -> list:
    """Walk any GraphQL response shape and pull out problem nodes."""
    out = []
    if not isinstance(node, dict):
        return out

    # Is this node a problem?
    has_grade = any(k in node for k in [
        "grade", "vGrade", "v_grade", "difficulty", "font_grade", "hueco_grade"
    ])
    has_name = any(k in node for k in ["name", "title"])

    if has_name and has_grade:
        out.append({**node, "_area": area, "_subarea": subarea})
        return out

    node_name = node.get("name") or node.get("title") or ""

    for key, val in node.items():
        if key.startswith("_") or not isinstance(val, (dict, list)):
            continue
        children = val if isinstance(val, list) else [val]
        for child in children:
            if not isinstance(child, dict):
                continue
            child_name = child.get("name") or child.get("title") or ""
            if key in ("areas", "sub_areas", "subAreas", "sectors", "zones", "walls"):
                out += extract_problems(child, child_name or node_name, "")
            elif key in ("problems", "routes", "climbs", "boulders"):
                out += extract_problems(
                    child,
                    area or node_name,
                    subarea or node_name
                )
            elif key == "children":
                if area:
                    out += extract_problems(child, area, child_name or node_name)
                else:
                    out += extract_problems(child, child_name or node_name, "")
            else:
                out += extract_problems(
                    child,
                    area or node_name,
                    subarea
                )
    return out


# ── Normalize to site format ──────────────────────────────────────────────────

def normalize(p: dict) -> dict:
    def first(*keys):
        for k in keys:
            if p.get(k) is not None:
                return p[k]
        return None

    name     = first("name", "title") or "Unknown"
    gl_raw   = first("grade", "vGrade", "v_grade", "hueco_grade",
                     "gradeLabel", "difficulty") or "V?"
    gl       = str(gl_raw).strip().upper()
    if gl and not gl.startswith("V"):
        gl = f"V{gl}"
    m        = re.search(r"V(\d+)", gl)
    grade_n  = int(m.group(1)) if m else 0

    try:
        stars = max(0, min(3, round(float(
            first("stars", "rating", "quality", "star_rating") or 0
        ))))
    except (TypeError, ValueError):
        stars = 0

    desc     = first("description", "beta", "notes", "text", "body") or ""
    topo_url = first("topo_image_url", "topoImageUrl", "imageUrl",
                     "image_url", "image", "thumbnailUrl") or ""

    area    = p.get("_area") or "Little Cottonwood Canyon"
    subarea = p.get("_subarea") or "Main Area"
    sa_slug = slug(f"{slug(area)}-{slug(subarea)}")

    return {
        "id":          f"problem-{slug(name)}",
        "name":        name,
        "grade":       grade_n,
        "gradeLabel":  gl,
        "stars":       stars,
        "area":        area,
        "area_url":    f"areas/{slug(area)}.html",
        "subarea":     subarea,
        "subarea_url": f"subareas/{sa_slug}.html",
        "description": desc,
        "topo_url":    topo_url,
        "topo_img":    "placeholder.svg",
    }


# ── Build summary ─────────────────────────────────────────────────────────────

def print_summary(problems: list):
    by_area = defaultdict(lambda: defaultdict(list))
    for p in problems:
        by_area[p["area"]][p["subarea"]].append(p)

    print(f"\n{'='*50}")
    print(f"SUMMARY: {len(problems)} problems across {len(by_area)} area(s)")
    print("=" * 50)
    for aname, subareas in by_area.items():
        total = sum(len(ps) for ps in subareas.values())
        print(f"\n  {aname}  ({total} problems)")
        for saname, ps in subareas.items():
            grades = sorted(set(p["gradeLabel"] for p in ps))
            print(f"    {saname}: {len(ps)} problems  "
                  f"[{', '.join(grades[:6])}{'…' if len(grades)>6 else ''}]")


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    TOPOS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print("Kaya HAR Parser")
    print("=" * 50)

    # Load HAR
    gql_entries = load_har(HAR_FILE)
    if not gql_entries:
        return

    # Extract all problems
    raw_problems = []
    for entry in gql_entries:
        raw_problems += extract_problems(entry["data"])

    # De-duplicate by name
    seen, unique = set(), []
    for p in raw_problems:
        name = str(p.get("name") or "")
        if name and name not in seen:
            seen.add(name)
            unique.append(p)

    print(f"\nUnique problems extracted: {len(unique)}")

    if not unique:
        print("\nNo problems found in HAR.")
        print("Things to check:")
        print("  1. Did you browse all areas/sub-areas in the Kaya app before exporting?")
        print("  2. Is kaya-beta.kayaclimb.com visible in the mitmweb request list?")
        print("  3. Try filtering by 'kaya-beta' in mitmweb and check the response bodies.")
        return

    normalized = [normalize(p) for p in unique]
    print_summary(normalized)

    # Download topo images
    print("\nDownloading topo images…")
    for p in normalized:
        url = p.get("topo_url", "")
        if url and url.startswith("http"):
            ext  = Path(urlparse(url).path).suffix or ".jpg"
            dest = TOPOS_DIR / f"{slug(p['name'])}{ext}"
            if not dest.exists() and download_image(url, dest):
                p["topo_img"] = dest.name
                print(f"  Saved: {dest.name}")

    # Save output
    output = {
        "meta": {
            "scraped_at":     time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source":         "mitmproxy HAR",
            "problems_found": len(normalized),
        },
        "problems": normalized,
    }
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, default=str),
                           encoding="utf-8")
    print(f"\nSaved: {OUTPUT_FILE.name}  ({len(normalized)} problems)")
    print("\nNext step:  python generate_site.py")


if __name__ == "__main__":
    run()
