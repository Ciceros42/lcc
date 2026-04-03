"""
probe_topo4.py
==============
Round 4: Very close now. Key leads:
  - Climb.wall_set_id  → probably the WallTopo ID
  - WallTopo.photo_url → the image URL (worked, just had wrong ID)
  - wallTopoShape      → root query linking climbs to topo shapes

Usage
-----
  py probe_topo4.py
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


def gql_raw(query: str, variables: dict, token: str):
    r = requests.post(GRAPHQL_URL,
                      json={"query": query, "variables": variables},
                      headers=base_headers(token), timeout=20)
    return r.status_code, r.json() if r.status_code in (200, 400) else {"text": r.text[:300]}


def probe(label: str, query: str, variables: dict, token: str):
    print(f"\n{'─'*55}")
    print(f"  {label}")
    status, body = gql_raw(query, variables, token)
    print(f"  HTTP {status}")
    print(json.dumps(body, indent=2)[:2500])
    time.sleep(0.8)
    return body


def run():
    print("=" * 55)
    print("Kaya topo probe — round 4")
    print("=" * 55)

    token = load_token()
    print(f"Token: {token[:40]}…\n")

    # ── Step 1: Get wall_set_id from the test climb ───────────────────────────
    print("\n=== Step 1: Get Climb.wall_set_id ===")
    body = probe("climb.wall_set_id", f"""
        query {{ climb(id: "{TEST_ID}") {{ id name wall_set_id has_topo }} }}
    """, {}, token)

    wall_set_id = None
    try:
        wall_set_id = body["data"]["climb"]["wall_set_id"]
        print(f"\n  >>> wall_set_id = {wall_set_id}")
    except Exception:
        print("  >>> Could not extract wall_set_id")

    # ── Step 2: Use wall_set_id as WallTopo ID ────────────────────────────────
    print("\n=== Step 2: wallTopo(id=wall_set_id) — find photo_url ===")
    if wall_set_id:
        wt_fields = [
            "id photo_url location_id",
            "id photo_url location_id name",
        ]
        for fields in wt_fields:
            probe(f"wallTopo(wall_set_id) {{{fields}}}", f"""
                query {{ wallTopo(id: "{wall_set_id}") {{ {fields} }} }}
            """, {}, token)

        # Also try more WallTopo fields now we have a real ID
        for field in ["name", "location_id", "slug", "description",
                      "climb_shapes { id }", "shapes { id }",
                      "climbs { id name }"]:
            fname = field.split()[0]
            probe(f"WallTopo.{fname}", f"""
                query {{ wallTopo(id: "{wall_set_id}") {{ id photo_url {field} }} }}
            """, {}, token)
    else:
        print("  Skipping — no wall_set_id found")

    # ── Step 3: wallTopoShape root query ──────────────────────────────────────
    print("\n=== Step 3: wallTopoShape query ===")

    # First probe what args it takes
    probe("wallTopoShape — no args (find required args)", """
        query { wallTopoShape { id } }
    """, {}, token)

    # Try likely arg patterns
    for arg_name in ["climb_id", "id", "climbId", "wall_topo_id", "wallTopoId"]:
        probe(f"wallTopoShape({arg_name}=TEST_ID)", f"""
            query {{ wallTopoShape({arg_name}: "{TEST_ID}") {{ id }} }}
        """, {}, token)

    if wall_set_id:
        for arg_name in ["wall_topo_id", "id", "wallTopoId"]:
            probe(f"wallTopoShape({arg_name}=wall_set_id)", f"""
                query {{ wallTopoShape({arg_name}: "{wall_set_id}") {{ id }} }}
            """, {}, token)

    # ── Step 4: webClimb — try wall_set_id field ──────────────────────────────
    print("\n=== Step 4: webClimb.wall_set_id ===")
    probe("webClimb.wall_set_id", f"""
        query {{ webClimb(slug: "{TEST_SLUG}") {{ id name wall_set_id }} }}
    """, {}, token)

    # ── Step 5: climbsForLocation (non-web version, may have more fields) ─────
    print("\n=== Step 5: climbsForLocation ===")
    probe("climbsForLocation — what args?", """
        query { climbsForLocation { id name wall_set_id has_topo } }
    """, {}, token)

    probe("climbsForLocation(location_id, offset, count)", f"""
        query {{
          climbsForLocation(location_id: "6225", offset: 0, count: 2) {{
            id name wall_set_id has_topo
          }}
        }}
    """, {}, token)

    print("\n" + "=" * 55)
    print("Done.")


if __name__ == "__main__":
    run()
