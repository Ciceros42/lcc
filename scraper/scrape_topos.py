"""
scrape_topos.py
===============
Fetches wall topo image URLs for every climb in scraped_data.json.

Discovered chain:
  climbsForLocation(location_id) → climb.wall_topo_shapes { wall_topo_id }
  wallTopo(id: wall_topo_id)     → photo_url  (CDN URL)

Strategy (efficient — minimises API calls):
  Pass 1: paginate climbsForLocation for each of the 41 areas
          → build { climb_id: [wall_topo_id, ...] }   (~250 calls)
  Pass 2: batch-resolve unique wall_topo_ids
          → build { wall_topo_id: photo_url }          (~few hundred calls)
  Pass 3: update scraped_data.json problems with topo_img / topo_imgs

A climb that appears on >1 topo gets all URLs stored in topo_imgs (list).
topo_img is set to the first URL (backwards-compatible with existing code).

Usage
-----
  cd scraper
  py scrape_topos.py
"""

import json, os, re, time
from dotenv import load_dotenv
from pathlib import Path
from playwright.sync_api import sync_playwright, Request
import requests

load_dotenv()

SCRAPER_DIR  = Path(__file__).parent
TOKEN_FILE   = SCRAPER_DIR / "auth_token.txt"
DATA_FILE    = SCRAPER_DIR / "scraped_data.json"
CKPT_FILE    = SCRAPER_DIR / "checkpoint_climbs.json"
OUTPUT_FILE  = SCRAPER_DIR / "scraped_data.json"   # overwrite in place
GRAPHQL_URL  = "https://kaya-beta.kayaclimb.com/graphql"
LOGIN_URL    = "https://kaya-app.kayaclimb.com/login"

EMAIL    = os.getenv("KAYA_EMAIL", "")
PASSWORD = os.getenv("KAYA_PASSWORD", "")

PAGE_SIZE     = 20
REQUEST_DELAY = 1.2   # seconds between API calls
SAVE_EVERY    = 5     # save progress every N areas

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
    print("Token expired — opening browser to log in…")
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
        try:
            r = requests.post(GRAPHQL_URL,
                              json={"query": "{ currentUser { id } }"},
                              headers=base_headers(token), timeout=10)
            if r.status_code == 200 and r.json().get("data", {}).get("currentUser"):
                print("  Token still valid.")
                return token
        except Exception:
            pass
    return fresh_login()


def base_headers(token: str) -> dict:
    return {
        "Content-Type":  "application/json",
        "Authorization": token,
        "User-Agent":    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
        "Accept":        "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin":        "https://kaya-app.kayaclimb.com",
        "Referer":       "https://kaya-app.kayaclimb.com/",
    }


def gql(query: str, variables: dict, token: str,
        retries: int = 4, base_wait: float = 10.0) -> dict:
    for attempt in range(retries):
        r = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=base_headers(token),
            timeout=30,
        )
        if r.status_code == 403:
            raise RuntimeError("Cloudflare 403 — IP blocked. Wait and retry.")
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


# ── Queries ───────────────────────────────────────────────────────────────────

CLIMBS_TOPO_QUERY = """
query climbsForLocation($location_id: ID!, $offset: Int!, $count: Int!) {
  climbsForLocation(location_id: $location_id, offset: $offset, count: $count) {
    id
    name
    wall_topo_shapes {
      id
      wall_topo_id
      points
    }
  }
}
"""

WALL_TOPO_QUERY = """
query wallTopo($id: ID!) {
  wallTopo(id: $id) {
    id
    photo_url
  }
}
"""


def fetch_climbs_for_area(area_id: str, token: str) -> list[dict]:
    """Paginate climbsForLocation for one area, return list of climb dicts."""
    results = []
    offset  = 0
    while True:
        data = gql(CLIMBS_TOPO_QUERY,
                   {"location_id": area_id, "offset": offset, "count": PAGE_SIZE},
                   token)
        page = data.get("climbsForLocation") or []
        results.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(REQUEST_DELAY)
    return results


def fetch_wall_topo_url(topo_id: str, token: str) -> str | None:
    """Fetch photo_url for a single WallTopo ID."""
    data = gql(WALL_TOPO_QUERY, {"id": topo_id}, token)
    wt = data.get("wallTopo")
    return wt.get("photo_url") if wt else None


def extract_climb_id(slug: str) -> str | None:
    m = re.search(r"-(\d+)$", slug)
    return m.group(1) if m else None


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("=" * 60)
    print("Kaya Wall Topo Scraper")
    print("=" * 60)

    # Load scraped data
    data     = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    problems = data["problems"]
    print(f"Loaded {len(problems)} problems from {DATA_FILE.name}")

    # Load area IDs from checkpoint (has _area_id for each climb)
    ckpt_climbs = json.loads(CKPT_FILE.read_text(encoding="utf-8"))["climbs"]
    area_ids: dict[str, str] = {}  # area_id → area_name
    for c in ckpt_climbs:
        aid = c.get("_area_id")
        if aid:
            area_ids[aid] = c.get("_area_name", aid)
    print(f"Found {len(area_ids)} areas to scan\n")

    token = load_token()
    print(f"Token: {token[:40]}…\n")

    # ── Pass 1: build climb_id → [wall_topo_id, ...] ─────────────────────────
    print("=" * 60)
    print("PASS 1: Fetching wall_topo_shapes for all climbs")
    print("=" * 60)

    # Checkpoint for pass 1
    PASS1_CKPT = SCRAPER_DIR / "topo_pass1.json"
    done_areas:    set[str]        = set()
    climb_to_topo: dict[str, list] = {}  # climb_id → [wall_topo_id, ...]

    if PASS1_CKPT.exists():
        try:
            p1 = json.loads(PASS1_CKPT.read_text(encoding="utf-8"))
            done_areas    = set(p1.get("done_areas", []))
            climb_to_topo = p1.get("climb_to_topo", {})
            print(f"Resuming: {len(done_areas)} areas done, "
                  f"{len(climb_to_topo)} climbs mapped so far.\n")
        except Exception as e:
            print(f"Could not load pass-1 checkpoint ({e}), starting fresh.\n")

    area_list = sorted(area_ids.items())
    for i, (area_id, area_name) in enumerate(area_list, 1):
        if area_id in done_areas:
            print(f"  [{i}/{len(area_list)}] {area_name} — already done")
            continue

        print(f"  [{i}/{len(area_list)}] {area_name} (id={area_id})")
        try:
            climbs = fetch_climbs_for_area(area_id, token)
        except RuntimeError as e:
            print(f"\nFATAL: {e}")
            print("Saving checkpoint. Re-run after the block clears.")
            break

        with_topo = 0
        for c in climbs:
            cid    = str(c.get("id") or "")
            cname  = c.get("name") or ""
            shapes = c.get("wall_topo_shapes") or []
            topo_ids = [str(s["wall_topo_id"]) for s in shapes if s.get("wall_topo_id")]
            # Store full shape data: {id, wall_topo_id, points} per shape
            # shape 'id' = wallTopoShape.id, used to identify the specific route line per climb
            shape_data = [
                {"id": str(s["id"]), "wall_topo_id": str(s["wall_topo_id"]), "points": s.get("points") or ""}
                for s in shapes if s.get("wall_topo_id") and s.get("id")
            ]
            if topo_ids:
                climb_to_topo[cid] = topo_ids
                # Also index by name for cross-type ID matching
                if cname:
                    climb_to_topo[f"name:{cname}"] = topo_ids
                # Store shape points for per-climb route lines
                if shape_data:
                    climb_to_topo[f"shapes:{cid}"] = shape_data
                with_topo += 1

        print(f"    {len(climbs)} climbs, {with_topo} have topos")
        done_areas.add(area_id)

        if i % SAVE_EVERY == 0 or i == len(area_list):
            PASS1_CKPT.write_text(json.dumps({
                "done_areas":    list(done_areas),
                "climb_to_topo": climb_to_topo,
            }, indent=2), encoding="utf-8")
            print(f"    Checkpoint saved ({len(climb_to_topo)} climbs mapped)")

        time.sleep(REQUEST_DELAY)

    print(f"\nPass 1 done. {len(climb_to_topo)} climbs have topo associations.")

    # ── Pass 2: resolve unique wall_topo_ids → photo_url ─────────────────────
    print("\n" + "=" * 60)
    print("PASS 2: Resolving wall_topo_id → photo_url")
    print("=" * 60)

    all_topo_ids = {tid for tids in climb_to_topo.values() for tid in tids}
    print(f"Unique wall_topo_ids to resolve: {len(all_topo_ids)}")

    PASS2_CKPT = SCRAPER_DIR / "topo_pass2.json"
    topo_url: dict[str, str] = {}  # wall_topo_id → photo_url

    if PASS2_CKPT.exists():
        try:
            topo_url = json.loads(PASS2_CKPT.read_text(encoding="utf-8"))
            print(f"Resuming: {len(topo_url)} topo URLs already resolved.\n")
        except Exception:
            pass

    remaining = [tid for tid in all_topo_ids if tid not in topo_url]
    print(f"Still need to fetch: {len(remaining)}\n")

    for i, topo_id in enumerate(remaining, 1):
        if i % 50 == 0:
            pct = int(100 * i / len(remaining))
            print(f"  [{i}/{len(remaining)} {pct}%] resolving topo IDs…")
        try:
            url = fetch_wall_topo_url(topo_id, token)
            if url:
                topo_url[topo_id] = url
        except RuntimeError as e:
            print(f"\nFATAL: {e}")
            print("Saving checkpoint. Re-run after the block clears.")
            break
        except Exception as e:
            print(f"  Error on topo_id {topo_id}: {e}")

        if i % 100 == 0:
            PASS2_CKPT.write_text(json.dumps(topo_url, indent=2), encoding="utf-8")

        time.sleep(REQUEST_DELAY)

    PASS2_CKPT.write_text(json.dumps(topo_url, indent=2), encoding="utf-8")
    print(f"\nPass 2 done. Resolved {len(topo_url)} topo URLs.")

    # ── Pass 3: update scraped_data.json ──────────────────────────────────────
    print("\n" + "=" * 60)
    print("PASS 3: Updating problems with topo URLs")
    print("=" * 60)

    updated = 0
    multi   = 0
    missing = 0

    for p in problems:
        cid = extract_climb_id(p.get("slug", ""))

        # Try numeric ID match first, then fall back to name match
        topo_ids = None
        shape_data = None
        if cid and cid in climb_to_topo:
            topo_ids   = climb_to_topo[cid]
            shape_data = climb_to_topo.get(f"shapes:{cid}")
        else:
            name_key = f"name:{p.get('name', '')}"
            if name_key in climb_to_topo:
                topo_ids = climb_to_topo[name_key]
                # Try to find shape data via any numeric key that maps to same topos
                for k, v in climb_to_topo.items():
                    if not k.startswith("name:") and not k.startswith("shapes:") and v == topo_ids:
                        shape_data = climb_to_topo.get(f"shapes:{k}")
                        break

        if not topo_ids:
            missing += 1
            continue

        photo_urls = [topo_url[tid] for tid in topo_ids if tid in topo_url]

        if not photo_urls:
            missing += 1
            continue

        p["topo_img"]  = photo_urls[0]      # first topo (backwards-compat)
        p["topo_imgs"] = photo_urls          # all topos
        if shape_data:
            p["topo_shapes"] = shape_data   # [{wall_topo_id, points}, ...]
        updated += 1
        if len(photo_urls) > 1:
            multi += 1

    print(f"  Updated:  {updated}")
    print(f"  Multiple topos: {multi}")
    print(f"  No topo found:  {missing}")

    data["problems"] = problems
    OUTPUT_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved: {OUTPUT_FILE.name}")
    print("Next step: py generate_site.py")


if __name__ == "__main__":
    run()
