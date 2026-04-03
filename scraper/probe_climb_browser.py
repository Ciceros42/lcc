"""
probe_climb_browser.py
======================
Uses a Playwright browser session (bypasses Cloudflare) to:
  1. Log in to Kaya
  2. Navigate to a sample climb's share URL
  3. Capture what GraphQL queries fire — especially anything with photo/topo URLs
  4. Also directly fetch climb data via browser's own fetch() to test webClimb query

Usage:  python probe_climb_browser.py
"""
import json, os, time
from dotenv import load_dotenv
from pathlib import Path
from playwright.sync_api import sync_playwright, Request, Response

load_dotenv()
GRAPHQL_URL = "https://kaya-beta.kayaclimb.com/graphql"
LOGIN_URL   = "https://kaya-app.kayaclimb.com/login"
EMAIL    = os.getenv("KAYA_EMAIL", "")
PASSWORD = os.getenv("KAYA_PASSWORD", "")

# Sample climb — "The Surfboard Problem" at 5 Mile
CLIMB_SLUG = "Surfboard-Problem-v4-Little-Cottonwood-Canyon-130746"
CLIMB_ID   = "130746"

captured: list[dict] = []
auth_token: list[str] = []


def on_request(req: Request):
    if GRAPHQL_URL not in req.url:
        return
    try:
        hdrs = dict(req.headers)
        if hdrs.get("authorization") and not auth_token:
            auth_token.append(hdrs["authorization"])
        body = req.post_data_json
        if body:
            captured.append({
                "operation": body.get("operationName", "(unnamed)"),
                "variables": body.get("variables", {}),
                "response": None,
            })
            print(f"  [→] {body.get('operationName','?')}  {str(body.get('variables',''))[:60]}")
    except Exception:
        pass


def on_response(resp: Response):
    if GRAPHQL_URL not in resp.url:
        return
    try:
        data = resp.json().get("data")
        for entry in reversed(captured):
            if entry["response"] is None:
                entry["response"] = data
                break
    except Exception:
        pass


def run():
    with sync_playwright() as pw:
        iphone  = pw.devices["iPhone 14 Pro"]
        browser = pw.chromium.launch(headless=False)
        ctx     = browser.new_context(**iphone)
        page    = ctx.new_page()
        page.on("request",  on_request)
        page.on("response", on_response)

        # ── Login ─────────────────────────────────────────────────────────────
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
        time.sleep(5)

        # ── Try share URL for the climb ───────────────────────────────────────
        share_url = f"https://kaya-app.kayaclimb.com/share/location?id={CLIMB_ID}"
        print(f"\nNavigating to climb share URL: {share_url}")
        captured.clear()
        page.goto(share_url, wait_until="load", timeout=60_000)
        time.sleep(6)
        page.mouse.wheel(0, 800)
        time.sleep(3)

        # ── Use browser fetch() to call webClimb directly ─────────────────────
        print("\nTrying webClimb(slug) via browser fetch()…")
        if auth_token:
            token = auth_token[0]
            result = page.evaluate("""
                async ([url, token, slug]) => {
                    const r = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': token,
                            'Origin': 'https://kaya-app.kayaclimb.com',
                        },
                        body: JSON.stringify({
                            operationName: 'webClimb',
                            query: `query webClimb($slug: String!) {
                              webClimb(slug: $slug) {
                                id slug name description
                                topo_url photo_url rating
                                grade { name }
                                area { id name }
                                __typename
                              }
                            }`,
                            variables: { slug }
                        })
                    });
                    return await r.json();
                }
            """, [GRAPHQL_URL, token, CLIMB_SLUG])
            print("webClimb response:")
            print(json.dumps(result, indent=2)[:1500])
        else:
            print("  No token captured yet.")

        # ── Try webClimbForSlug if webClimb failed ────────────────────────────
        if auth_token:
            token = auth_token[0]
            result2 = page.evaluate("""
                async ([url, token, id]) => {
                    const r = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': token,
                            'Origin': 'https://kaya-app.kayaclimb.com',
                        },
                        body: JSON.stringify({
                            operationName: 'climb',
                            query: `query climb($id: ID!) {
                              climb(id: $id) {
                                id name description
                                topo_url photo_url rating
                                grade { name }
                                location { id name }
                                __typename
                              }
                            }`,
                            variables: { id }
                        })
                    });
                    return await r.json();
                }
            """, [GRAPHQL_URL, token, CLIMB_ID])
            print("\nclimb(id) response:")
            print(json.dumps(result2, indent=2)[:1500])

        browser.close()

    # ── Print captured operations ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Captured {len(captured)} GraphQL operations from share URL page:")
    for e in captured:
        print(f"  {e['operation']}  →  keys: {list((e['response'] or {}).keys())[:5]}")

    # Save token for reuse
    if auth_token:
        Path(__file__).parent.joinpath("auth_token.txt").write_text(
            json.dumps({"headers": {"authorization": auth_token[0]}}, indent=2),
            encoding="utf-8"
        )
        print(f"\nFresh token saved.")


if __name__ == "__main__":
    run()
