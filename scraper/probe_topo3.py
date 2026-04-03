"""
probe_topo3.py
==============
Round 3: Targeted probes based on discovered leads:
  - wallTopo(id: ID!) exists — find its fields
  - wallToposForClimb / wallTopoForClimb root query
  - Climb.has_topo boolean
  - WallTopo fields: url, photo_url, image, slug, climbs, etc.

Usage
-----
  py probe_topo3.py
"""

import json, os, time
from dotenv import load_dotenv
from pathlib import Path
from playwright.sync_api import sync_playwright, Request
import requests

load_dotenv()

SCRAPER_DIR = Path(__file__).parent
TOKEN_FILE  = SCRAPER_DIR / "auth_token.txt"
GRAPHQL_URL = "https://kaya-beta.kayaclimb.com/graphql"
LOGIN_URL   = "https://kaya-app.kayaclimb.com/login"

EMAIL    = os.getenv("KAYA_EMAIL", "")
PASSWORD = os.getenv("KAYA_PASSWORD", "")

TEST_SLUG = "Surfboard-Problem-v4-Little-Cottonwood-Canyon-130746"
TEST_ID   = "130746"
AREA_ID   = "6225"

fresh_headers: dict = {}


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
    print("Token expired — opening browser…")
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


def probe(label: str, query: str, variables: dict, token: str):
    print(f"\n{'─'*55}")
    print(f"  {label}")
    r = requests.post(GRAPHQL_URL,
                      json={"query": query, "variables": variables},
                      headers=base_headers(token), timeout=20)
    print(f"  HTTP {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2)[:2500])
    except Exception:
        print(r.text[:500])
    time.sleep(0.8)


def run():
    print("=" * 55)
    print("Kaya topo probe — round 3")
    print("=" * 55)

    token = load_token()
    print(f"Token: {token[:40]}…\n")

    # ── 1. Confirm has_topo on Climb ──────────────────────────────────────────
    print("\n=== Part 1: Climb.has_topo ===")
    probe("climb.has_topo", f"""
        query {{ climb(id: "{TEST_ID}") {{ id name has_topo }} }}
    """, {}, token)

    # ── 2. wallToposForClimb / wallTopoForClimb root queries ──────────────────
    print("\n=== Part 2: *ForClimb root queries ===")
    for qname in [
        "wallTopoForClimb",
        "wallToposForClimb",
        "wallToposByClimb",
        "topoForClimb",
        "toposForClimb",
    ]:
        probe(f"root: {qname}(climb_id)", f"""
            query {{ {qname}(climb_id: "{TEST_ID}") {{ id }} }}
        """, {}, token)
        time.sleep(0.5)

    # Also try the ID arg pattern (wallTopo uses id not climb_id)
    for qname in [
        "wallTopoForClimb",
        "wallToposForClimb",
    ]:
        probe(f"root: {qname}(id)", f"""
            query {{ {qname}(id: "{TEST_ID}") {{ id }} }}
        """, {}, token)
        time.sleep(0.5)

    # ── 3. wallTopo(id) — probe WallTopo type fields ──────────────────────────
    # We know wallTopo(id: ID!) exists and WallTopo type exists
    # Use the topo CDN IDs we already have from the boulder HTML
    # From 5-mile-cheese-whiz-cheese-whiz.html: sktwi1ogflnme83fg
    print("\n=== Part 3: WallTopo type fields ===")

    # First try with the climb's numeric ID (might not be a valid WallTopo ID)
    wt_fields = [
        "id",
        "url",
        "photo_url",
        "image_url",
        "image",
        "src",
        "slug",
        "file_url",
        "asset_url",
        "cdn_url",
        "jpeg_url",
        "location { id name }",
        "climbs { id name }",
        "climb_shapes { id }",
        "shapes { id }",
        "boulder { id name }",
        "wall { id name }",
    ]
    for field in wt_fields:
        fname = field.split()[0]
        probe(f"wallTopo(climb_id).{fname}", f"""
            query {{ wallTopo(id: "{TEST_ID}") {{ id {field} }} }}
        """, {}, token)

    # ── 4. wallToposForLocation — maybe get all topos for an area ─────────────
    print("\n=== Part 4: wallTopos* for location ===")
    for qname in [
        "wallToposForLocation",
        "wallTopoForLocation",
        "wallTopos",
    ]:
        probe(f"root: {qname}(location_id)", f"""
            query {{ {qname}(location_id: "{AREA_ID}") {{ id }} }}
        """, {}, token)
        probe(f"root: {qname}(id)", f"""
            query {{ {qname}(id: "{AREA_ID}") {{ id }} }}
        """, {}, token)
        time.sleep(0.3)

    # ── 5. Probe Climb type for more fields (bolts, photos, tags, has_topo) ───
    print("\n=== Part 5: Climb full field survey ===")
    climb_fields = [
        "has_topo",
        "bolts",
        "tags { id name }",
        "photos { url }",
        "color { id name }",
        "photo_url",
        "video_url",
        "grade { name }",
        "location",
        "wall_topo_id",
        "topo_id",
        "rp_wall_topo_id",
    ]
    for field in climb_fields:
        fname = field.split()[0]
        probe(f"climb.{fname}", f"""
            query {{ climb(id: "{TEST_ID}") {{ id name {field} }} }}
        """, {}, token)

    print("\n" + "=" * 55)
    print("Done.")


if __name__ == "__main__":
    run()
