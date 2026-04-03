"""
probe_topo6.py
==============
Final verification: walk the full chain
  climb(id) → wall_topo_shapes { wall_topo_id } → wallTopo(id) { photo_url }

If this works, we build the scraper next.

Usage
-----
  py probe_topo6.py
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

# Test with a few different climbs to confirm the pattern
TEST_CLIMBS = [
    ("130746", "The Surfboard Problem"),
    ("628821", "Big Mouth"),
    ("131068", "Baldy Right"),
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


def post(query: str, variables: dict, token: str) -> dict:
    r = requests.post(GRAPHQL_URL,
                      json={"query": query, "variables": variables},
                      headers=base_headers(token), timeout=20)
    return r.json()


def run():
    print("=" * 55)
    print("Kaya topo probe — round 6 (final verification)")
    print("=" * 55)

    token = load_token()
    print(f"Token: {token[:40]}…\n")

    # ── Step 1: Get wall_topo_shapes with wall_topo_id ────────────────────────
    print("\n=== Step 1: climb → wall_topo_shapes { id wall_topo_id } ===\n")
    for climb_id, name in TEST_CLIMBS:
        body = post(f"""
            query {{
              climb(id: "{climb_id}") {{
                id name has_topo
                wall_topo_shapes {{
                  id
                  wall_topo_id
                }}
              }}
            }}
        """, {}, token)
        print(f"  {name} (id={climb_id}):")
        print(json.dumps(body, indent=2)[:1500])
        print()
        time.sleep(1)

    # ── Step 2: Use wall_topo_id to fetch WallTopo.photo_url ─────────────────
    print("\n=== Step 2: wallTopo(wall_topo_id) → photo_url ===\n")

    # Get shapes for first test climb
    body = post(f"""
        query {{
          climb(id: "130746") {{
            wall_topo_shapes {{ id wall_topo_id }}
          }}
        }}
    """, {}, token)

    shapes = []
    try:
        shapes = body["data"]["climb"]["wall_topo_shapes"] or []
    except Exception:
        print("  Could not extract shapes")

    print(f"  Got {len(shapes)} shapes for Surfboard Problem")
    for shape in shapes:
        wt_id = shape.get("wall_topo_id")
        s_id  = shape.get("id")
        print(f"\n  WallTopoShape id={s_id}, wall_topo_id={wt_id}")
        if wt_id:
            wt_body = post(f"""
                query {{
                  wallTopo(id: "{wt_id}") {{
                    id
                    photo_url
                    location_id
                  }}
                }}
            """, {}, token)
            print(f"  wallTopo({wt_id}):")
            print(json.dumps(wt_body, indent=2))
        time.sleep(1)

    # ── Step 3: wallTopoShape(id) — confirm its fields ────────────────────────
    print("\n=== Step 3: wallTopoShape(id=25651) — known shape ID ===\n")
    body = post("""
        query {
          wallTopoShape(id: "25651") {
            id
            wall_topo_id
          }
        }
    """, {}, token)
    print(json.dumps(body, indent=2))

    print("\n" + "=" * 55)
    print("Done.")


if __name__ == "__main__":
    run()
