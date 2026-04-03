"""
probe_topo.py
=============
Probes the Kaya GraphQL API to find which field(s) on webClimb
hold the wall topo image URL (the rp_wall_topo CDN link).

Strategy:
  1. Introspect the WebClimb type to list ALL available fields
  2. Try specific topo-related field name guesses
  3. Print full responses so we can see what data is available

Usage
-----
  cd scraper
  python probe_topo.py
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

# A well-known climb slug to use as the test subject
TEST_SLUG = "Surfboard-Problem-v4-Little-Cottonwood-Canyon-130746"

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
                print("  Saved token still valid.")
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


def gql(query: str, variables: dict, token: str) -> dict:
    r = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers=base_headers(token),
        timeout=20,
    )
    return {"status": r.status_code, "body": r.json() if r.status_code in (200, 400) else r.text}


def probe(label: str, query: str, variables: dict, token: str):
    print(f"\n{'─'*55}")
    print(f"  {label}")
    result = gql(query, variables, token)
    print(f"  HTTP {result['status']}")
    print(json.dumps(result["body"], indent=2)[:2000])


def run():
    print("=" * 55)
    print("Kaya topo field probe")
    print(f"Test slug: {TEST_SLUG}")
    print("=" * 55)

    token = load_token()
    print(f"Token: {token[:40]}…\n")

    # ── 1. Introspect WebClimb type — lists ALL fields ─────────────────────────
    probe("Introspect WebClimb type (all fields)",
        "{ __type(name: \"WebClimb\") { fields { name type { name kind ofType { name kind } } } } }",
        {}, token)

    time.sleep(1)

    # ── 2. Introspect Climb type (fallback) ────────────────────────────────────
    probe("Introspect Climb type (all fields)",
        "{ __type(name: \"Climb\") { fields { name type { name kind ofType { name kind } } } } }",
        {}, token)

    time.sleep(1)

    # ── 3. Try topo-related field names on webClimb ────────────────────────────
    topo_fields = [
        "topo_url",
        "topo_image_url",
        "wall_topo_url",
        "rp_wall_topo_url",
        "topo { id image_url }",
        "topos { id image_url }",
        "wall_topo { id image_url }",
        "wall_topos { id image_url }",
        "rp_wall_topo { id image_url }",
        "rp_wall_topos { id image_url }",
        "shape { id image_url }",
        "shapes { id image_url }",
        "climb_shape { id image_url }",
        "climb_shapes { id image_url }",
    ]

    for field in topo_fields:
        query = """
            query webClimb($slug: String!) {
              webClimb(slug: $slug) {
                id
                name
                %s
              }
            }
        """ % field
        probe(f"webClimb.{field.split()[0]}", query, {"slug": TEST_SLUG}, token)
        time.sleep(1)

    # ── 4. Dump the full webClimb response with known-good fields ──────────────
    # to see if any topo-adjacent fields are visible in the raw response
    probe("webClimb — full known fields",
        """
        query webClimb($slug: String!) {
          webClimb(slug: $slug) {
            id slug name description rating
            grade { name }
            area { id name }
            __typename
          }
        }
        """,
        {"slug": TEST_SLUG}, token)

    print("\n" + "=" * 55)
    print("Done. Look for HTTP 200 responses above — those fields exist.")
    print("GraphQL error messages also hint at valid field names.")


if __name__ == "__main__":
    run()
