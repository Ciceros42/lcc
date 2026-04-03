"""
scrape_subareas.py
==================
Phase 3 — Sub-area / boulder location scraper.
Drills down one level below each of the 42 LCC areas to fetch
their child locations (individual boulder clusters / sub-zones),
each with its own lat/lng coordinates.

Run AFTER scrape_kaya_v2.py (needs scraped_data.json).
Run independently from scrape_details.py (topo photos).

Output
------
  scraper/scraped_subareas.json   — all sub-area / boulder location data
  data/problems.js                — rebuilt with sub-area coords added
  areas/*.html                    — rebuilt with sub-area map markers

Usage
-----
  python scrape_subareas.py
"""

import json, os, re, time
from dotenv import load_dotenv
from pathlib import Path
from playwright.sync_api import sync_playwright, Request
import requests

load_dotenv()

SCRAPER_DIR   = Path(__file__).parent
ROOT          = SCRAPER_DIR.parent
TOKEN_FILE    = SCRAPER_DIR / "auth_token.txt"
DATA_FILE     = SCRAPER_DIR / "scraped_data.json"
OUTPUT_FILE   = SCRAPER_DIR / "scraped_subareas.json"
GRAPHQL_URL   = "https://kaya-beta.kayaclimb.com/graphql"
LOGIN_URL     = "https://kaya-app.kayaclimb.com/login"

EMAIL    = os.getenv("KAYA_EMAIL", "")
PASSWORD = os.getenv("KAYA_PASSWORD", "")

BOULDER_TYPE   = "1"
PAGE_SIZE      = 20
REQUEST_DELAY  = 1.5
SAVE_EVERY     = 10

fresh_headers: dict = {}


# ── Auth (same pattern as other scrapers) ─────────────────────────────────────

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
    print("Token expired — logging in…")
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
        time.sleep(8)
        browser.close()
    token = fresh_headers.get("authorization", "")
    if token:
        TOKEN_FILE.write_text(
            json.dumps({"headers": {"authorization": token}}, indent=2),
            encoding="utf-8",
        )
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
        try:
            r = requests.post(GRAPHQL_URL,
                              json={"query": "{ currentUser { id } }"},
                              headers=base_headers(token), timeout=10)
            if r.status_code == 200 and r.json().get("data", {}).get("currentUser"):
                print("  Saved token is still valid.")
                return token
        except Exception:
            pass
    return fresh_login()


def base_headers(token: str) -> dict:
    return {
        "Content-Type":    "application/json",
        "Authorization":   token,
        "User-Agent":      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
        "Accept":          "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin":          "https://kaya-app.kayaclimb.com",
        "Referer":         "https://kaya-app.kayaclimb.com/",
    }


# ── GraphQL ───────────────────────────────────────────────────────────────────

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


def gql(query: str, variables: dict, token: str,
        retries: int = 5, base_wait: float = 8.0) -> dict:
    for attempt in range(retries):
        r = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=base_headers(token),
            timeout=30,
        )
        if r.status_code == 403:
            raise RuntimeError("Cloudflare 403 — IP blocked. Wait a few hours and retry.")
        body = r.json()
        if r.status_code == 200 and "errors" not in body:
            return body.get("data", {})
        errs = body.get("errors", [])
        msg  = errs[0]["message"] if errs else r.text[:200]
        if any(kw in msg.lower() for kw in ["try again", "rate", "limit", "timeout"]):
            wait = base_wait * (2 ** attempt)
            print(f"    [rate-limit] waiting {wait:.0f}s…")
            time.sleep(wait)
            continue
        raise RuntimeError(f"GraphQL error: {msg}")
    raise RuntimeError(f"Failed after {retries} retries")


def fetch_children(location_id: str, token: str) -> list[dict]:
    """Fetch all child locations of a given location ID (paginated)."""
    results = []
    offset  = 0
    while True:
        variables = {
            "location_id":   location_id,
            "climb_type_id": BOULDER_TYPE,
            "offset":        offset,
            "count":         PAGE_SIZE,
        }
        data = gql(LOCATIONS_QUERY, variables, token)
        page = data.get("webLocationsForLocation") or []
        results.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(REQUEST_DELAY)
    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("=" * 60)
    print("Kaya Sub-area / Boulder Location Scraper")
    print("=" * 60)

    if not DATA_FILE.exists():
        print(f"ERROR: {DATA_FILE} not found. Run scrape_kaya_v2.py first.")
        return

    data  = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    areas = data.get("areas", [])
    print(f"Loaded {len(areas)} areas from {DATA_FILE.name}\n")

    token = load_token()
    print(f"Token: {token[:40]}…\n")

    # Load checkpoint
    CHECKPOINT = SCRAPER_DIR / "checkpoint_subareas.json"
    done_ids:    set[str]   = set()
    all_subareas: list[dict] = []

    if CHECKPOINT.exists():
        try:
            ckpt        = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
            done_ids    = set(ckpt.get("done_area_ids", []))
            all_subareas = ckpt.get("subareas", [])
            print(f"Resuming: {len(done_ids)} areas done, {len(all_subareas)} sub-areas so far.\n")
        except Exception as e:
            print(f"Could not load checkpoint ({e}), starting fresh.\n")

    # ── Fetch sub-areas for each top-level area ────────────────────────────────
    for i, area in enumerate(areas, 1):
        area_id   = str(area.get("id") or "")
        area_name = area["name"]

        if not area_id:
            print(f"  [{i}/{len(areas)}] {area_name} — no ID, skipping.")
            continue

        if area_id in done_ids:
            print(f"  [{i}/{len(areas)}] {area_name} — already done.")
            continue

        boulder_count = area.get("problemCount") or "?"
        print(f"  [{i}/{len(areas)}] {area_name}  (id={area_id}, ~{boulder_count} problems)")

        try:
            children = fetch_children(area_id, token)
        except RuntimeError as e:
            print(f"\nFATAL: {e}")
            print("Saving checkpoint. Re-run after the block clears.")
            break

        if children:
            for child in children:
                child["_parent_id"]   = area_id
                child["_parent_name"] = area_name
            all_subareas.extend(children)
            print(f"    → {len(children)} sub-areas found")
        else:
            print(f"    → no sub-areas (leaf area)")

        done_ids.add(area_id)

        # Save checkpoint
        if i % SAVE_EVERY == 0 or i == len(areas):
            CHECKPOINT.write_text(json.dumps({
                "done_area_ids": list(done_ids),
                "subareas":      all_subareas,
            }, default=str), encoding="utf-8")
            print(f"    Checkpoint saved ({len(all_subareas)} sub-areas total)")

        time.sleep(REQUEST_DELAY)

    # ── Save final output ──────────────────────────────────────────────────────
    # Deduplicate by id
    seen: set[str] = set()
    unique_subareas = []
    for s in all_subareas:
        if s["id"] not in seen:
            seen.add(s["id"])
            unique_subareas.append(s)

    output = {
        "meta": {
            "scraped_at":    time.strftime("%Y-%m-%dT%H:%M:%S"),
            "areas_scanned": len(done_ids),
            "subareas_found": len(unique_subareas),
        },
        "subareas": unique_subareas,
    }
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"Done. {len(unique_subareas)} sub-areas/boulders across {len(done_ids)} areas.")
    print(f"Saved: {OUTPUT_FILE.name}")

    # Summary
    has_coords = sum(1 for s in unique_subareas if s.get("latitude") and s.get("longitude"))
    print(f"Sub-areas with coordinates: {has_coords}/{len(unique_subareas)}")
    print("\nTop areas by sub-area count:")
    from collections import Counter
    counts = Counter(s["_parent_name"] for s in unique_subareas)
    for name, count in counts.most_common(10):
        print(f"  {name:40s} {count} sub-areas")

    print(f"\nNext step: python update_map_subareas.py")


if __name__ == "__main__":
    run()
