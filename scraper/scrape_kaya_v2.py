"""
scrape_kaya_v2.py
=================
Fetches all bouldering problems in Little Cottonwood Canyon from Kaya's API
using the discovered GraphQL queries.

Strategy:
  1. Load or refresh auth token (Playwright login)
  2. Fetch all bouldering areas under LCC  (webLocationsForLocation, paginated)
  3. For each area, fetch all its climbs   (webClimbsForLocation, paginated)
  4. Fetch individual climb details        (webClimb or climb, for description/topo)
  5. Save scraped_data.json for generate_site.py

Usage
-----
  python scrape_kaya_v2.py
"""

import json
import os
import re
import time
from dotenv import load_dotenv
from pathlib import Path
from playwright.sync_api import sync_playwright, Request
import requests

load_dotenv()

TOKEN_FILE   = Path(__file__).parent / "auth_token.txt"
OUTPUT_FILE  = Path(__file__).parent / "scraped_data.json"
GRAPHQL_URL  = "https://kaya-beta.kayaclimb.com/graphql"
LOGIN_URL    = "https://kaya-app.kayaclimb.com/login"
LCC_ID       = "6146"
BOULDER_TYPE = "1"   # climb_type_id for bouldering
PAGE_SIZE    = 20    # items per page (API enforces a count limit)

EMAIL    = os.getenv("KAYA_EMAIL", "")
PASSWORD = os.getenv("KAYA_PASSWORD", "")

fresh_headers: dict = {}


# ── Auth ──────────────────────────────────────────────────────────────────────

def on_request(req: Request):
    if GRAPHQL_URL not in req.url:
        return
    try:
        hdrs = dict(req.headers)
        if hdrs.get("authorization"):
            fresh_headers["authorization"] = hdrs["authorization"]
    except Exception:
        pass


def fresh_login() -> str:
    print("Token expired or missing — logging in…")
    with sync_playwright() as pw:
        iphone  = pw.devices["iPhone 14 Pro"]
        browser = pw.chromium.launch(headless=False)
        ctx     = browser.new_context(**iphone)
        page    = ctx.new_page()
        page.on("request", on_request)
        page.goto(LOGIN_URL, wait_until="load", timeout=60_000)
        time.sleep(2)
        for sel in ['input[type="email"]', 'input[name="email"]']:
            try: page.fill(sel, EMAIL, timeout=3000); break
            except Exception: continue
        for sel in ['input[type="password"]', 'input[name="password"]']:
            try: page.fill(sel, PASSWORD, timeout=3000); break
            except Exception: continue
        for sel in ['button[type="submit"]', 'button:has-text("Sign in")']:
            try: page.click(sel, timeout=3000); break
            except Exception: continue
        time.sleep(6)
        browser.close()
    token = fresh_headers.get("authorization", "")
    if token:
        TOKEN_FILE.write_text(
            json.dumps({"headers": {"authorization": token}}, indent=2),
            encoding="utf-8",
        )
        print("  Token saved.")
    return token


def load_token() -> str:
    token = ""
    if TOKEN_FILE.exists():
        try:
            token = (json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
                     .get("headers", {}).get("authorization", ""))
        except Exception:
            pass
    if token:
        hdrs = base_headers(token)
        try:
            r = requests.post(GRAPHQL_URL,
                              json={"query": "{ currentUser { id } }"},
                              headers=hdrs, timeout=10)
            if r.status_code == 200 and r.json().get("data", {}).get("currentUser"):
                print("  Saved token is still valid.")
                return token
        except Exception:
            pass
    return fresh_login()


def base_headers(token: str) -> dict:
    return {
        "Content-Type":  "application/json",
        "Authorization": token,
        "User-Agent":    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        "Origin":        "https://kaya-app.kayaclimb.com",
        "Referer":       "https://kaya-app.kayaclimb.com/",
    }


# ── GraphQL helpers ───────────────────────────────────────────────────────────

def gql(query: str, variables: dict, token: str,
        retries: int = 5, base_wait: float = 8.0) -> dict:
    """Execute a GraphQL query with exponential-backoff retry on rate-limit errors."""
    for attempt in range(retries):
        r = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=base_headers(token),
            timeout=30,
        )
        body = r.json()
        if r.status_code == 200 and "errors" not in body:
            return body.get("data", {})

        errs = body.get("errors", [])
        msg  = errs[0]["message"] if errs else r.text[:200]

        # Retry on transient server errors
        if any(kw in msg.lower() for kw in ["try again", "rate", "limit", "timeout", "503", "502"]):
            wait = base_wait * (2 ** attempt)
            print(f"    [rate-limit] {msg!r} — waiting {wait:.0f}s (attempt {attempt+1}/{retries})")
            time.sleep(wait)
            continue

        raise RuntimeError(f"GraphQL error: {msg}")

    raise RuntimeError(f"GraphQL failed after {retries} retries")


def fetch_all_pages(query: str, variables_base: dict,
                    key: str, token: str, page_size: int = PAGE_SIZE) -> list:
    """Paginate through a query and return all results."""
    results = []
    offset  = 0
    while True:
        variables = {**variables_base, "offset": offset, "count": page_size}
        data = gql(query, variables, token)
        page = data.get(key, []) or []
        results.extend(page)
        print(f"    fetched {len(results)} (page +{len(page)})")
        if len(page) < page_size:
            break
        offset += page_size
        time.sleep(1.0)   # 1s between pages to avoid rate limits
    return results


# ── GraphQL queries ───────────────────────────────────────────────────────────

LOCATIONS_QUERY = """
query webLocationsForLocation(
    $location_id: ID!, $offset: Int!, $count: Int!, $climb_type_id: ID
) {
  webLocationsForLocation(
      location_id: $location_id, offset: $offset,
      count: $count, climb_type_id: $climb_type_id
  ) {
    id
    slug
    name
    latitude
    longitude
    photo_url
    description
    description_bouldering
    access_description_bouldering
    climb_count
    boulder_count
    is_access_sensitive
    is_closed
    location_type { id name __typename }
    __typename
  }
}
"""

CLIMBS_QUERY = """
query webClimbsForLocation(
    $location_id: ID!, $climb_name: String, $climb_type_id: ID,
    $offset: Int!, $count: Int!
) {
  webClimbsForLocation(
      location_id: $location_id, climb_name: $climb_name,
      climb_type_id: $climb_type_id, offset: $offset, count: $count
  ) {
    slug
    name
    rating
    ascent_count
    grade { id name __typename }
    climb_type { name __typename }
    area { name __typename }
    destination { name __typename }
    is_gb_moderated
    is_access_sensitive
    is_closed
    __typename
  }
}
"""

CLIMB_DETAIL_QUERY = """
query webClimb($slug: String!) {
  webClimb(slug: $slug) {
    slug
    name
    description
    rating
    ascent_count
    grade { id name __typename }
    area { id name slug __typename }
    destination { id name __typename }
    topo_url
    photo_url
    is_gb_moderated
    __typename
  }
}
"""


def extract_id_from_slug(slug: str) -> str:
    """Extract numeric ID from end of Kaya slug, e.g. 'Twisted-v4-...-130955' → '130955'."""
    m = re.search(r"-(\d+)$", slug)
    return m.group(1) if m else ""


def vgrade_number(grade_name: str) -> int:
    """Convert grade name like 'v4', 'V3' to int."""
    m = re.match(r"[vV](\d+)", grade_name.strip())
    return int(m.group(1)) if m else 0


# ── Main scrape ───────────────────────────────────────────────────────────────

def run():
    print("=" * 60)
    print("Kaya LCC Scraper v2")
    print("=" * 60)

    token = load_token()
    print(f"Using token: {token[:40]}…\n")

    # ── Step 1: Fetch all bouldering areas under LCC ──────────────────────────
    print("Step 1: Fetching bouldering areas under LCC…")
    areas = fetch_all_pages(
        LOCATIONS_QUERY,
        {"location_id": LCC_ID, "climb_type_id": BOULDER_TYPE},
        "webLocationsForLocation",
        token,
    )
    print(f"  Total areas found: {len(areas)}\n")

    if not areas:
        print("ERROR: No areas returned. Check token / query.")
        return

    # ── Step 2: For each area, fetch all its bouldering climbs ────────────────
    print("Step 2: Fetching climbs for each area…")

    # Load checkpoint if it exists (allows resuming after a crash)
    CHECKPOINT = Path(__file__).parent / "checkpoint_climbs.json"
    done_ids: set[str] = set()
    all_climbs: list[dict] = []
    area_map: dict[str, dict] = {}

    if CHECKPOINT.exists():
        try:
            ckpt = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
            all_climbs = ckpt.get("climbs", [])
            done_ids   = set(ckpt.get("done_area_ids", []))
            area_map   = {a["name"]: a for a in ckpt.get("area_metas", [])}
            print(f"  Resuming from checkpoint: {len(done_ids)} areas done, "
                  f"{len(all_climbs)} climbs so far.")
        except Exception as e:
            print(f"  Could not load checkpoint ({e}); starting fresh.")

    for i, area in enumerate(areas, 1):
        area_name = area["name"]
        area_id   = area["id"]
        count     = area.get("boulder_count") or area.get("climb_count") or "?"

        if area_id in done_ids:
            print(f"  [{i}/{len(areas)}] {area_name}  — already done, skipping.")
            area_map[area_name] = area
            continue

        print(f"  [{i}/{len(areas)}] {area_name}  (id={area_id}, ~{count} problems)")
        area_map[area_name] = area

        climbs = fetch_all_pages(
            CLIMBS_QUERY,
            {"location_id": area_id, "climb_type_id": BOULDER_TYPE, "climb_name": ""},
            "webClimbsForLocation",
            token,
        )
        for c in climbs:
            c["_area_id"]   = area_id
            c["_area_name"] = area_name
        all_climbs.extend(climbs)
        done_ids.add(area_id)

        # Save checkpoint after each area
        CHECKPOINT.write_text(json.dumps({
            "done_area_ids": list(done_ids),
            "climbs":        all_climbs,
            "area_metas":    list(area_map.values()),
        }, default=str), encoding="utf-8")

        time.sleep(1.5)   # pause between areas

    print(f"\nTotal climbs fetched: {len(all_climbs)}")

    # ── Step 3: Optionally fetch climb detail for description/topo ────────────
    # We try the webClimb(slug) query on one sample to see if it works.
    sample = all_climbs[0] if all_climbs else None
    has_web_climb = False
    if sample:
        try:
            detail = gql(CLIMB_DETAIL_QUERY, {"slug": sample["slug"]}, token)
            if detail.get("webClimb"):
                has_web_climb = True
                print("  webClimb(slug) query works — will fetch descriptions.")
        except Exception as e:
            print(f"  webClimb(slug) not available ({e}) — skipping descriptions.")

    # ── Step 4: Build output in generate_site.py format ───────────────────────
    problems = []
    seen_slugs: set[str] = set()

    for c in all_climbs:
        slug  = c.get("slug", "")
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        grade_obj = c.get("grade") or {}
        grade_name = grade_obj.get("name", "")   # e.g. "v4"
        grade_label = grade_name.upper()
        if grade_label and not grade_label.startswith("V"):
            grade_label = f"V{grade_label}"
        grade_num = vgrade_number(grade_label)

        # Rating: Kaya uses 1–4 scale (or null). Map to 0–3 stars.
        rating_raw = c.get("rating")
        try:
            stars = max(0, min(3, round(float(rating_raw)))) if rating_raw else 0
        except (TypeError, ValueError):
            stars = 0

        area_name = c.get("_area_name") or (c.get("area") or {}).get("name") or "Unknown Area"

        problems.append({
            "id":          f"problem-{slug}",
            "slug":        slug,
            "name":        c.get("name") or "Unknown",
            "grade":       grade_num,
            "gradeLabel":  grade_label or "V?",
            "stars":       stars,
            "ascent_count": c.get("ascent_count") or 0,
            "area":        area_name,
            "area_url":    f"areas/{re.sub(r'[^a-z0-9]+', '-', area_name.lower()).strip('-')}.html",
            "subarea":     area_name,
            "subarea_url": f"subareas/{re.sub(r'[^a-z0-9]+', '-', area_name.lower()).strip('-')}.html",
            "description": "",
            "topo_img":    "placeholder.svg",
        })

    # ── Step 5: Fetch descriptions if webClimb works ──────────────────────────
    if has_web_climb:
        print(f"\nStep 5: Fetching descriptions for {len(problems)} climbs…")
        for i, p in enumerate(problems):
            if i % 50 == 0:
                print(f"  {i}/{len(problems)}…")
            try:
                detail = gql(CLIMB_DETAIL_QUERY, {"slug": p["slug"]}, token)
                wc = detail.get("webClimb") or {}
                p["description"] = wc.get("description") or ""
                topo = wc.get("topo_url") or wc.get("photo_url") or ""
                if topo:
                    p["topo_img"] = topo
            except Exception:
                pass
            time.sleep(0.15)

    # ── Step 6: Build area list ───────────────────────────────────────────────
    areas_out = []
    from collections import defaultdict
    by_area: dict[str, list] = defaultdict(list)
    for p in problems:
        by_area[p["area"]].append(p)

    for aname, ps in by_area.items():
        area_meta = area_map.get(aname, {})
        grades    = sorted(p["grade"] for p in ps)
        areas_out.append({
            "id":           re.sub(r"[^a-z0-9]+", "-", aname.lower()).strip("-"),
            "name":         aname,
            "url":          f"areas/{re.sub(r'[^a-z0-9]+', '-', aname.lower()).strip('-')}.html",
            "gradeRange":   f"V{grades[0]}–V{grades[-1]}" if grades else "V?",
            "problemCount": len(ps),
            "latitude":     area_meta.get("latitude"),
            "longitude":    area_meta.get("longitude"),
            "description":  area_meta.get("description_bouldering") or area_meta.get("description") or "",
            "access":       area_meta.get("access_description_bouldering") or "",
            "photo_url":    area_meta.get("photo_url") or "",
        })

    areas_out.sort(key=lambda a: a["name"])

    # ── Step 7: Save ──────────────────────────────────────────────────────────
    output = {
        "meta": {
            "scraped_at":     time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source":         "Kaya GraphQL (webLocationsForLocation + webClimbsForLocation)",
            "lcc_id":         LCC_ID,
            "areas_found":    len(areas_out),
            "problems_found": len(problems),
        },
        "areas":    areas_out,
        "problems": problems,
    }
    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"\n{'='*60}")
    print(f"Done! {len(problems)} problems across {len(areas_out)} areas.")
    print(f"Saved: {OUTPUT_FILE}")
    print("\nAreas found:")
    for a in areas_out:
        print(f"  {a['name']:40s} {a['problemCount']:4d} problems  {a['gradeRange']}")
    print(f"\nNext step: python generate_site.py")


if __name__ == "__main__":
    run()
