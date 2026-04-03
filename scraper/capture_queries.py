"""
capture_queries.py
==================
Logs in to Kaya, navigates the share/location URL for LCC, and captures
every GraphQL request + response the app makes. Prints operation names,
variables, and response shapes so we can identify how child areas/climbs
are fetched.

Usage
-----
  python capture_queries.py
"""

import json
import os
import time
from dotenv import load_dotenv
from pathlib import Path
from playwright.sync_api import sync_playwright, Request, Response

load_dotenv()

TOKEN_FILE  = Path(__file__).parent / "auth_token.txt"
GRAPHQL_URL = "https://kaya-beta.kayaclimb.com/graphql"
LOGIN_URL   = "https://kaya-app.kayaclimb.com/login"
LCC_URL     = "https://kaya-app.kayaclimb.com/share/location?id=6146&childId=null"
LCC_ID      = "6146"

EMAIL    = os.getenv("KAYA_EMAIL", "")
PASSWORD = os.getenv("KAYA_PASSWORD", "")

captured: list[dict] = []
fresh_headers: dict = {}


def on_request(req: Request):
    if GRAPHQL_URL not in req.url:
        return
    try:
        hdrs = dict(req.headers)
        if hdrs.get("authorization"):
            fresh_headers["authorization"] = hdrs["authorization"]
        body = req.post_data_json
        if body:
            entry = {
                "operation": body.get("operationName", "(unnamed)"),
                "variables": body.get("variables", {}),
                "query_snippet": (body.get("query") or "")[:200],
                "response": None,
            }
            captured.append(entry)
            print(f"  [→ GQL] {entry['operation']}  vars={json.dumps(entry['variables'])[:80]}")
    except Exception as e:
        print(f"  [req err] {e}")


def on_response(resp: Response):
    if GRAPHQL_URL not in resp.url:
        return
    try:
        body = resp.json()
        data = body.get("data") or body.get("errors")
        # Match to last unresolved captured entry
        for entry in reversed(captured):
            if entry["response"] is None:
                entry["response"] = data
                break
    except Exception:
        pass


def load_token() -> str:
    if TOKEN_FILE.exists():
        try:
            data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            return data.get("headers", {}).get("authorization", "")
        except Exception:
            pass
    return ""


def run():
    token = load_token()

    with sync_playwright() as pw:
        iphone  = pw.devices["iPhone 14 Pro"]
        browser = pw.chromium.launch(headless=False)
        ctx     = browser.new_context(**iphone)
        page    = ctx.new_page()

        page.on("request",  on_request)
        page.on("response", on_response)

        # ── Step 1: Log in ────────────────────────────────────────────────────
        print("Logging in…")
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

        print("  Waiting for login to complete…")
        time.sleep(6)
        print(f"  Token captured: {bool(fresh_headers.get('authorization'))}")

        # ── Step 2: Navigate to LCC share URL ────────────────────────────────
        print(f"\nNavigating to LCC share URL…\n  {LCC_URL}")
        captured.clear()
        page.goto(LCC_URL, wait_until="load", timeout=60_000)
        print("  Page loaded — waiting 8s for lazy-loaded GraphQL calls…")
        time.sleep(8)

        # ── Step 3: Try scrolling/interacting to trigger more requests ────────
        print("  Scrolling to trigger more content loads…")
        page.mouse.wheel(0, 500)
        time.sleep(3)
        page.mouse.wheel(0, 500)
        time.sleep(3)

        # ── Step 4: Try clicking on any area/sub-area links ───────────────────
        print("  Looking for tappable location/area links…")
        try:
            links = page.locator("a[href*='location'], a[href*='area'], a[href*='climb']").all()
            print(f"  Found {len(links)} location-style links")
            if links:
                print(f"  First link text: {links[0].text_content()}")
                links[0].click(timeout=3000)
                time.sleep(5)
        except Exception as e:
            print(f"  No clickable links found ({e})")

        browser.close()

    # ── Print summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"CAPTURED {len(captured)} GraphQL operations:")
    print("=" * 60)

    for i, entry in enumerate(captured, 1):
        print(f"\n[{i}] Operation: {entry['operation']}")
        print(f"    Variables: {json.dumps(entry['variables'], indent=6)[:300]}")
        print(f"    Query:     {entry['query_snippet']}")
        if entry["response"] is not None:
            resp_str = json.dumps(entry["response"], indent=4)[:500]
            print(f"    Response:  {resp_str}")
        else:
            print(f"    Response:  (not captured)")

    # Save full capture to file
    out = Path(__file__).parent / "captured_queries.json"
    out.write_text(json.dumps(captured, indent=2, default=str), encoding="utf-8")
    print(f"\nFull capture saved to: {out.name}")


if __name__ == "__main__":
    run()
