"""
probe_topo5.py
==============
Round 5:
  - Use real WallTopo CDN IDs (from boulder HTML) as wallTopo(id)
  - Probe WallTopoShape fields
  - Try Climb.wallTopoShape, Climb.wall_topo_shape
  - Try climbsForLocation with topo-adjacent fields

Usage
-----
  py probe_topo5.py
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

TEST_ID   = "130746"   # The Surfboard Problem
AREA_ID   = "6225"     # 5 Mile

# Real WallTopo CDN IDs extracted from boulders/5-mile-cheese-whiz-cheese-whiz.html
# URL pattern: assets.plastick.rocks/prod/rp_wall_topo/{ID}.jpeg
REAL_TOPO_IDS = [
    "sktwi1ogflnme83fg",
    "sktwi1ogflnme84s1",
    "sktwi1ogflnme85yo",
    "sktwi1ogflnme8738",
    "sktwi1ogflnme886q",
]

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
    print("Kaya topo probe — round 5")
    print("=" * 55)

    token = load_token()
    print(f"Token: {token[:40]}…\n")

    # ── 1. Use real CDN IDs as wallTopo(id) ───────────────────────────────────
    print("\n=== Part 1: wallTopo with real CDN IDs ===")
    for topo_id in REAL_TOPO_IDS[:2]:  # test first 2
        probe(f"wallTopo(id={topo_id[:12]}…)", f"""
            query {{ wallTopo(id: "{topo_id}") {{
                id
                photo_url
                location_id
            }} }}
        """, {}, token)

    # ── 2. WallTopoShape fields — probe with a real topo CDN ID as shape ID ──
    print("\n=== Part 2: wallTopoShape fields ===")
    # WallTopoShape takes id: ID! — probe what fields it has
    probe("wallTopoShape(id=topo_id) — find fields", f"""
        query {{ wallTopoShape(id: "{REAL_TOPO_IDS[0]}") {{ id }} }}
    """, {}, token)

    # Probe WallTopoShape field names via error messages using a dummy ID
    wts_fields = [
        "photo_url",
        "image_url",
        "points",
        "coordinates",
        "path",
        "climb { id name }",
        "climb_id",
        "wall_topo { id photo_url }",
        "wall_topo_id",
        "shape_type",
        "type",
        "color",
        "label",
    ]
    for field in wts_fields:
        fname = field.split()[0]
        probe(f"WallTopoShape.{fname}", f"""
            query {{ wallTopoShape(id: "{REAL_TOPO_IDS[0]}") {{ id {field} }} }}
        """, {}, token)

    # ── 3. Climb with topo-shape relation fields ───────────────────────────────
    print("\n=== Part 3: Climb topo-shape relation fields ===")
    climb_fields = [
        "wallTopoShape { id }",
        "wall_topo_shape { id }",
        "wallTopoShapes { id }",
        "wall_topo_shapes { id }",
        "topo_shape { id }",
        "topo_shapes { id }",
        "wall_set { id }",
        "wallSet { id }",
    ]
    for field in climb_fields:
        fname = field.split()[0]
        probe(f"climb.{fname}", f"""
            query {{ climb(id: "{TEST_ID}") {{ id name {field} }} }}
        """, {}, token)

    # ── 4. climbsForLocation with extended fields ─────────────────────────────
    print("\n=== Part 4: climbsForLocation extended fields ===")
    extra = [
        "wallTopoShape { id }",
        "wall_topo_shape { id }",
        "topo_shape { id }",
        "photos { url }",
        "photo_url",
        "description",
    ]
    for field in extra:
        fname = field.split()[0]
        probe(f"climbsForLocation.{fname}", f"""
            query {{
              climbsForLocation(location_id: "{AREA_ID}", offset: 0, count: 1) {{
                id name {field}
              }}
            }}
        """, {}, token)

    # ── 5. WallTopo — try more field names now we may have real IDs ────────────
    print("\n=== Part 5: WallTopo extended fields ===")
    if REAL_TOPO_IDS:
        tid = REAL_TOPO_IDS[0]
        wt_extra = [
            "wallTopoShapes { id climb_id }",
            "wall_topo_shapes { id climb_id }",
            "shapes { id climb { id name } }",
            "climb_shapes { id climb { id name } }",
            "climbs { id name }",
            "name",
            "description",
        ]
        for field in wt_extra:
            fname = field.split()[0]
            probe(f"WallTopo.{fname}", f"""
                query {{ wallTopo(id: "{tid}") {{ id photo_url {field} }} }}
            """, {}, token)

    print("\n" + "=" * 55)
    print("Done.")


if __name__ == "__main__":
    run()
