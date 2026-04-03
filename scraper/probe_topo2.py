"""
probe_topo2.py
==============
Round 2: topo data is NOT on WebClimb. Now probing:
  - climb type (non-web, by numeric ID)
  - webClimbsForLocation with extra fields
  - root-level shape/topo queries
  - webLocation with shape sub-fields
  - map out ALL WebClimb fields by brute-forcing names

Usage
-----
  py probe_topo2.py
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

# Known climb: "The Surfboard Problem" id=130746, in area id=6225 (5 Mile)
TEST_SLUG  = "Surfboard-Problem-v4-Little-Cottonwood-Canyon-130746"
TEST_ID    = "130746"
AREA_ID    = "6225"   # 5 Mile — a small area, good for testing

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


def probe(label: str, query: str, variables: dict, token: str):
    print(f"\n{'─'*55}")
    print(f"  {label}")
    r = requests.post(GRAPHQL_URL,
                      json={"query": query, "variables": variables},
                      headers=base_headers(token), timeout=20)
    print(f"  HTTP {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2)[:2000])
    except Exception:
        print(r.text[:500])
    time.sleep(0.8)


def run():
    print("=" * 55)
    print("Kaya topo probe — round 2")
    print("=" * 55)

    token = load_token()
    print(f"Token: {token[:40]}…\n")

    # ── 1. Map out ALL WebClimb scalar fields ─────────────────────────────────
    # We know: id, slug, name, description, rating, grade, area, __typename, color, climb_type
    # Try everything else we can think of
    print("\n=== Part 1: WebClimb field survey ===")
    webclimb_fields = [
        "photo_url",
        "photos { url }",
        "video_url",
        "ascent_count",
        "is_closed",
        "is_access_sensitive",
        "is_gb_moderated",
        "location { id name }",
        "parent { id name }",
        "destination { id name }",
        "boulder { id name }",
        "wall { id name }",
        "sector { id name }",
        "color { id name }",
        "climb_type { id name }",
    ]
    for field in webclimb_fields:
        fname = field.split()[0]
        probe(f"WebClimb.{fname}", f"""
            query {{ webClimb(slug: "{TEST_SLUG}") {{ id name {field} }} }}
        """, {}, token)

    # ── 2. climb type (non-web) with topo fields ──────────────────────────────
    print("\n=== Part 2: climb type (numeric ID) ===")
    probe("climb(id) — base fields", f"""
        query {{ climb(id: "{TEST_ID}") {{
            id name description rating photo_url
            photos {{ url }}
            grade {{ name }}
            location {{ id name }}
            __typename
        }} }}
    """, {}, token)

    climb_topo_fields = [
        "shape { id image_url points }",
        "shapes { id image_url points }",
        "topo { id image_url }",
        "topos { id image_url }",
        "wall_topo { id image_url }",
        "rp_wall_topo { id image_url }",
        "climb_shapes { id }",
        "route_shape { id image_url }",
        "topo_shape { id image_url }",
    ]
    for field in climb_topo_fields:
        fname = field.split()[0]
        probe(f"climb.{fname}", f"""
            query {{ climb(id: "{TEST_ID}") {{ id name {field} }} }}
        """, {}, token)

    # ── 3. Root-level topo/shape queries ──────────────────────────────────────
    print("\n=== Part 3: root-level topo queries ===")
    root_queries = [
        f'climbShape(climb_id: "{TEST_ID}") {{ id image_url }}',
        f'climbShape(id: "{TEST_ID}") {{ id image_url }}',
        f'climbShapes(climb_id: "{TEST_ID}") {{ id image_url }}',
        f'wallTopo(climb_id: "{TEST_ID}") {{ id image_url }}',
        f'wallTopo(id: "{TEST_ID}") {{ id image_url }}',
        f'rpWallTopo(id: "{TEST_ID}") {{ id image_url }}',
        f'rpWallTopos(climb_id: "{TEST_ID}") {{ id image_url }}',
        f'topoForClimb(climb_id: "{TEST_ID}") {{ id image_url }}',
        f'topoForClimb(id: "{TEST_ID}") {{ id image_url }}',
        f'climbTopo(climb_id: "{TEST_ID}") {{ id image_url }}',
        f'climbTopo(id: "{TEST_ID}") {{ id image_url }}',
    ]
    for q in root_queries:
        root_name = q.split("(")[0]
        probe(f"root: {root_name}", f"query {{ {q} }}", {}, token)

    # ── 4. webClimbsForLocation with extra fields ─────────────────────────────
    print("\n=== Part 4: webClimbsForLocation with topo fields ===")
    extra_fields = [
        "photo_url",
        "topo_url",
        "wall_topo { id image_url }",
        "shape { id image_url }",
        "shapes { id image_url }",
        "climb_shapes { id image_url }",
    ]
    for field in extra_fields:
        fname = field.split()[0]
        probe(f"webClimbsForLocation.{fname}", f"""
            query {{
              webClimbsForLocation(
                location_id: "{AREA_ID}", climb_type_id: "1",
                offset: 0, count: 1
              ) {{
                slug name {field}
              }}
            }}
        """, {}, token)

    # ── 5. webLocation for the boulder — does it expose topo+climb mapping? ───
    print("\n=== Part 5: webLocation with topo/shape sub-fields ===")
    # 5 Mile area slug
    AREA_SLUG = "5-Mile-Little-Cottonwood-Canyon-6225"
    wl_fields = [
        "topos { id image_url climbs { id name } }",
        "wall_topos { id image_url climbs { id name } }",
        "rp_wall_topos { id image_url }",
        "shapes { id image_url climb { id name } }",
        "climb_shapes { id image_url climb { id name } }",
        "topo_climbs { topo { image_url } climb { id name } }",
    ]
    for field in wl_fields:
        fname = field.split()[0]
        probe(f"webLocation.{fname}", f"""
            query {{ webLocation(slug: "{AREA_SLUG}") {{ id name {field} }} }}
        """, {}, token)

    # ── 6. Try webLocation with a boulder-level slug ───────────────────────────
    # The Cheese Whiz boulder might have a webLocation entry
    print("\n=== Part 6: boulder-level webLocation ===")
    # Try fetching webLocationsForLocation for area 6225, then check topo fields on those
    probe("webLocationsForLocation — child boulders", """
        query {
          webLocationsForLocation(
            location_id: "6225", climb_type_id: "1",
            offset: 0, count: 3
          ) {
            id slug name
            photo_url
          }
        }
    """, {}, token)

    print("\n" + "=" * 55)
    print("Done. HTTP 200 = field exists. Check error messages for hints.")


if __name__ == "__main__":
    run()
