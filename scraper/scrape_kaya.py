"""
scrape_kaya.py
==============
Uses the saved auth token to:
  1. Inject auth into a Playwright browser session
  2. Navigate to the LCC area page (via share URL)
  3. Capture the real GraphQL queries AND responses Kaya makes
  4. Parse the responses to extract areas, sub-areas, and problems

Usage
-----
  python scrape_kaya.py

Output
------
  scraped_data.json        — structured problem data
  auth_token.txt           — saved/refreshed auth token
  captured_queries.json    — raw GraphQL traffic (for debugging)
  ../images/topos/         — downloaded topo images
"""

import json
import os
import re
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import requests as req_lib
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Route, Request, Response

load_dotenv()

EMAIL    = os.getenv("KAYA_EMAIL", "")
PASSWORD = os.getenv("KAYA_PASSWORD", "")
LCC_URL  = os.getenv("KAYA_LCC_URL", "").strip()

GRAPHQL_URL  = "https://kaya-beta.kayaclimb.com/graphql"
APP_BASE     = "https://kaya-app.kayaclimb.com"
LOGIN_URL    = f"{APP_BASE}/login"

SCRAPER_DIR  = Path(__file__).parent
ROOT         = SCRAPER_DIR.parent
TOPOS_DIR    = ROOT / "images" / "topos"
OUTPUT_FILE  = SCRAPER_DIR / "scraped_data.json"
TOKEN_FILE   = SCRAPER_DIR / "auth_token.txt"
QUERIES_FILE = SCRAPER_DIR / "captured_queries.json"

# Mutable stores filled by network interceptors
auth_headers: dict  = {}
gql_traffic:  list  = []   # {"query": ..., "variables": ..., "response": ...}


# ── Network interceptors ──────────────────────────────────────────────────────

def on_request(request: Request):
    if GRAPHQL_URL not in request.url:
        return
    try:
        hdrs = dict(request.headers)
        for key in ["authorization", "x-auth-token", "cookie"]:
            if hdrs.get(key):
                auth_headers[key] = hdrs[key]
        body = request.post_data
        if body:
            parsed = json.loads(body)
            op = parsed.get("operationName", "?")
            print(f"  [→ GQL] {op}")
            gql_traffic.append({"request": parsed, "response": None})
    except Exception:
        pass


def on_response(response: Response):
    if GRAPHQL_URL not in response.url:
        return
    try:
        body = response.text()
        data = json.loads(body)
        # Attach to the last matching request
        for entry in reversed(gql_traffic):
            if entry["response"] is None:
                entry["response"] = data
                op = entry["request"].get("operationName", "?")
                has_data = bool(data.get("data"))
                print(f"  [← GQL] {op}  data={has_data}  errors={bool(data.get('errors'))}")
                break
    except Exception:
        pass


# ── Auth helpers ──────────────────────────────────────────────────────────────

def load_token() -> str | None:
    if TOKEN_FILE.exists():
        try:
            saved = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            hdrs  = saved.get("headers", {})
            token = hdrs.get("authorization", "")
            if token:
                auth_headers.update(hdrs)
                return token
        except Exception:
            pass
    return None


def save_token():
    TOKEN_FILE.write_text(json.dumps(
        {"headers": auth_headers, "sample_queries": gql_traffic[:3]},
        indent=2, default=str
    ), encoding="utf-8")


def test_token(token: str) -> bool:
    """Replay currentUser to confirm the token is still valid."""
    query = """query currentUser {
      currentUser { id email fname lname __typename }
    }"""
    hdrs = {
        "Content-Type": "application/json",
        "Authorization": token,
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        "Origin": APP_BASE,
    }
    try:
        resp = req_lib.post(GRAPHQL_URL, json={"operationName": "currentUser",
                                                "variables": {},
                                                "query": query},
                            headers=hdrs, timeout=15)
        data = resp.json()
        user = data.get("data", {}).get("currentUser")
        if user:
            print(f"  Token valid — logged in as: {user.get('email')}")
            return True
    except Exception as e:
        print(f"  Token test error: {e}")
    return False


# ── Login with Playwright ─────────────────────────────────────────────────────

def login_and_capture() -> bool:
    """Open mobile browser, log in, capture auth token."""
    print("\n  Opening browser to log in and capture token…")

    with sync_playwright() as pw:
        iphone  = pw.devices["iPhone 14 Pro"]
        browser = pw.chromium.launch(headless=False)
        ctx     = browser.new_context(**iphone)
        page    = ctx.new_page()
        page.on("request",  on_request)
        page.on("response", on_response)

        page.goto(LOGIN_URL, wait_until="load", timeout=60_000)
        time.sleep(2)

        # Fill login form
        for sel in ['input[type="email"]', 'input[name="email"]',
                    'input[placeholder*="email" i]']:
            try:
                page.fill(sel, EMAIL, timeout=3000)
                print(f"  Filled email")
                break
            except Exception:
                continue

        for sel in ['input[type="password"]', 'input[name="password"]',
                    'input[placeholder*="password" i]']:
            try:
                page.fill(sel, PASSWORD, timeout=3000)
                print(f"  Filled password")
                break
            except Exception:
                continue

        for sel in ['button[type="submit"]', 'button:has-text("Sign in")',
                    'button:has-text("Log in")']:
            try:
                page.click(sel, timeout=3000)
                print(f"  Submitted login form")
                break
            except Exception:
                continue

        # Wait for post-login traffic
        time.sleep(6)
        page.wait_for_load_state("load", timeout=30_000)

        if not auth_headers:
            print("\n  *** Could not auto-capture token ***")
            print("  Please log in manually in the browser, then press ENTER.")
            input("  Press ENTER after logging in… ")

        browser.close()

    if auth_headers:
        save_token()
        print(f"  Auth headers captured: {list(auth_headers.keys())}")
        return True

    print("  ERROR: No auth headers captured.")
    return False


# ── Navigate to LCC and capture GraphQL traffic ───────────────────────────────

def capture_lcc_data(token: str, lcc_url: str) -> list:
    """
    Open Kaya in a mobile browser with auth injected, navigate to the LCC
    area page, and capture all GraphQL responses.
    """
    print(f"\n  Opening Kaya at: {lcc_url}")
    print("  Capturing GraphQL traffic — please wait…")

    with sync_playwright() as pw:
        iphone  = pw.devices["iPhone 14 Pro"]
        browser = pw.chromium.launch(headless=False)
        ctx     = browser.new_context(**iphone)
        page    = ctx.new_page()
        page.on("request",  on_request)
        page.on("response", on_response)

        # First load the app root so we can inject auth into localStorage
        page.goto(APP_BASE, wait_until="load", timeout=60_000)
        time.sleep(1)

        # Inject the auth token into localStorage under common key names
        raw_token = token.replace("Bearer ", "")
        page.evaluate(f"""() => {{
            localStorage.setItem('token', '{raw_token}');
            localStorage.setItem('kaya_token', '{raw_token}');
            localStorage.setItem('authToken', '{raw_token}');
            localStorage.setItem('jwt', '{raw_token}');
            localStorage.setItem('access_token', '{raw_token}');
        }}""")

        # Navigate to LCC
        page.goto(lcc_url, wait_until="load", timeout=60_000)
        time.sleep(3)

        # Scroll to trigger lazy loading
        print("  Scrolling to load all content…")
        for _ in range(6):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

        # Try to expand any collapsed sections / tap sub-areas
        for sel in ['[data-testid*="area"]', '[class*="area"]', '[class*="sector"]',
                    'button:has-text("See all")', 'button:has-text("Show more")']:
            try:
                items = page.query_selector_all(sel)
                for item in items[:5]:
                    try:
                        item.click()
                        time.sleep(1)
                    except Exception:
                        pass
            except Exception:
                pass

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)

        print(f"\n  Total GraphQL exchanges captured: {len(gql_traffic)}")

        # If we got nothing useful, give user a chance to navigate manually
        useful = [t for t in gql_traffic
                  if t["response"] and t["response"].get("data")
                  and t["request"].get("operationName", "") != "currentUser"]

        if not useful:
            print("\n  *** Few/no climbing data queries captured ***")
            print("  In the browser window, try tapping into a boulder area or sub-area.")
            print("  Navigate around to trigger data loading, then press ENTER.")
            input("  Press ENTER when done browsing… ")

        browser.close()

    # Save all captured traffic for inspection
    QUERIES_FILE.write_text(json.dumps(gql_traffic, indent=2, default=str),
                            encoding="utf-8")
    print(f"  Saved raw traffic → {QUERIES_FILE.name}")
    return gql_traffic


# ── Direct GraphQL with captured query format ─────────────────────────────────

def query_with_captured_format(token: str, lcc_id: str) -> list:
    """
    Use the real query format observed in traffic to fetch LCC data directly.
    Tries common field combinations that match Kaya's snake_case style.
    """
    hdrs = {
        "Content-Type": "application/json",
        "Authorization": token,
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        "Origin": APP_BASE,
        "Referer": APP_BASE + "/",
    }

    results = []

    queries = [
        # Try the location query in multiple field-name styles
        ("GetLocation_v1", """query GetLocation($id: ID!) {
          location(id: $id) {
            id name description lat lng __typename
            areas {
              id name description __typename
              problems {
                id name grade stars description topoImageUrl imageUrl __typename
              }
            }
          }
        }""", {"id": lcc_id}),

        ("GetLocation_v2", """query GetLocation($id: ID!) {
          location(id: $id) {
            id name description __typename
            sub_areas {
              id name __typename
              problems { id name grade stars description topo_image_url __typename }
            }
          }
        }""", {"id": lcc_id}),

        ("GetArea_v1", """query GetArea($id: ID!) {
          area(id: $id) {
            id name description __typename
            problems {
              id name grade stars description topoImageUrl __typename
            }
            sub_areas {
              id name __typename
              problems { id name grade stars description __typename }
            }
          }
        }""", {"id": lcc_id}),

        ("GetGuide_v1", """query GetGuide($id: ID!) {
          guide(id: $id) {
            id name description __typename
            areas {
              id name __typename
              problems { id name grade stars description __typename }
            }
          }
        }""", {"id": lcc_id}),

        # Try browsing all locations
        ("AllLocations", """query {
          locations {
            id name state country __typename
          }
        }""", {}),

        # Try searching
        ("SearchAreas", """query SearchAreas($query: String!) {
          searchAreas(query: $query) {
            id name __typename
          }
        }""", {"query": "Little Cottonwood"}),
    ]

    for op_name, query, variables in queries:
        try:
            resp = req_lib.post(
                GRAPHQL_URL,
                json={"operationName": op_name, "variables": variables, "query": query},
                headers=hdrs, timeout=20
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("data"):
                print(f"  [✓] {op_name} returned data!")
                results.append(data["data"])
            elif data.get("errors"):
                errs = [e.get("message", "") for e in data["errors"]]
                print(f"  [✗] {op_name}: {'; '.join(errs[:2])}")
            else:
                print(f"  [✗] {op_name}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  [✗] {op_name}: {e}")

    return results


# ── Extract problems from any response shape ──────────────────────────────────

def extract_problems(node, area="", subarea="") -> list:
    out = []
    if not isinstance(node, dict):
        return out

    has_grade = any(k in node for k in ["grade","vGrade","v_grade","difficulty"])
    has_name  = any(k in node for k in ["name","title"])
    if has_name and has_grade:
        out.append({**node, "_area": area, "_subarea": subarea})
        return out

    node_name = node.get("name") or node.get("title") or ""
    for key, val in node.items():
        if not isinstance(val, (dict, list)):
            continue
        children = val if isinstance(val, list) else [val]
        for child in children:
            if not isinstance(child, dict):
                continue
            child_name = child.get("name") or ""
            if key in ("areas", "sub_areas", "subAreas", "sectors"):
                out += extract_problems(child, child_name, "")
            elif key in ("problems", "routes", "climbs"):
                out += extract_problems(child, area or node_name, subarea or node_name)
            elif key in ("children",):
                if area:
                    out += extract_problems(child, area, child_name or node_name)
                else:
                    out += extract_problems(child, child_name or node_name, "")
            else:
                out += extract_problems(child, area or node_name, subarea)
    return out


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def normalize(p: dict) -> dict:
    def first(*keys):
        for k in keys:
            if p.get(k) is not None:
                return p[k]
        return None

    name      = first("name", "title") or "Unknown"
    gl_raw    = first("grade","vGrade","v_grade","gradeLabel","difficulty") or "V?"
    gl        = str(gl_raw).upper().strip()
    if gl and not gl.startswith("V"):
        gl = f"V{gl}"
    m         = re.search(r"V(\d+)", gl)
    grade_num = int(m.group(1)) if m else 0

    try:
        stars = max(0, min(3, round(float(first("stars","rating","quality") or 0))))
    except (TypeError, ValueError):
        stars = 0

    desc      = first("description","beta","notes","text") or ""
    topo_url  = first("topoImageUrl","imageUrl","image","thumbnailUrl","topo_image_url") or ""
    area      = p.get("_area") or "Little Cottonwood Canyon"
    subarea   = p.get("_subarea") or "Main Area"
    sa_slug   = slug(f"{slug(area)}-{slug(subarea)}")

    return {
        "id":          f"problem-{slug(name)}",
        "name":        name,
        "grade":       grade_num,
        "gradeLabel":  gl,
        "stars":       stars,
        "area":        area,
        "area_url":    f"areas/{slug(area)}.html",
        "subarea":     subarea,
        "subarea_url": f"subareas/{sa_slug}.html",
        "description": desc,
        "topo_url":    topo_url,
        "topo_img":    "placeholder.svg",
    }


def download_image(url: str, dest: Path) -> bool:
    try:
        r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(r, timeout=15) as resp:
            dest.write_bytes(resp.read())
        return True
    except Exception:
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    TOPOS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Kaya Scraper — Little Cottonwood Canyon")
    print("=" * 60)

    # ── Step 1: Get valid auth token ──────────────────────────────────────────
    print("\n[1] Checking auth token…")
    token = load_token()
    if token and test_token(token):
        print("  Using saved token.")
    else:
        print("  Token missing or expired — logging in again…")
        TOKEN_FILE.unlink(missing_ok=True)
        auth_headers.clear()
        ok = login_and_capture()
        if not ok:
            print("ERROR: Could not obtain auth token.")
            return
        token = auth_headers.get("authorization", "")
        if not test_token(token):
            print("ERROR: Token obtained but currentUser query failed.")
            return

    # ── Step 2: Get LCC URL / ID ──────────────────────────────────────────────
    print("\n[2] Getting LCC location…")
    lcc_id = ""

    if LCC_URL:
        m = re.search(r"id[=:](\d+)", LCC_URL)
        if m:
            lcc_id = m.group(1)
            print(f"  Using LCC_URL from .env  →  id={lcc_id}")

    if not lcc_id:
        print("\n  To scrape LCC data, we need the Kaya location ID.")
        print("  Please open the Kaya app on your phone:")
        print("    1. Navigate to Little Cottonwood Canyon")
        print("    2. Tap the Share button")
        print("    3. Copy the link")
        print("  The link looks like: https://kaya-app.kayaclimb.com/share/location?id=XXXX")
        raw = input("\n  Paste the full URL or just the ID number: ").strip()
        m   = re.search(r"(\d+)", raw)
        if m:
            lcc_id = m.group(1)
            print(f"  Using id={lcc_id}")
            # Save it for next run
            env_path = SCRAPER_DIR / ".env"
            if env_path.exists():
                text = env_path.read_text(encoding="utf-8")
                text = re.sub(r"KAYA_LCC_URL=.*",
                              f"KAYA_LCC_URL=https://kaya-app.kayaclimb.com/share/location?id={lcc_id}",
                              text)
                env_path.write_text(text, encoding="utf-8")
                print(f"  Saved to .env for future runs.")
        else:
            print("  Could not parse an ID from that input.")
            return

    lcc_share_url = f"{APP_BASE}/share/location?id={lcc_id}"

    # ── Step 3: Try direct GraphQL first ─────────────────────────────────────
    print("\n[3] Querying GraphQL API directly…")
    direct_results = query_with_captured_format(token, lcc_id)

    # ── Step 4: If direct queries got nothing, open browser ──────────────────
    browser_traffic = []
    if not direct_results:
        print("\n[4] Direct queries returned no data — opening browser to capture traffic…")
        browser_traffic = capture_lcc_data(token, lcc_share_url)
    else:
        print("\n[4] Direct queries succeeded — skipping browser capture.")

    # ── Step 5: Extract problems from all sources ─────────────────────────────
    print("\n[5] Extracting problems…")
    raw_problems = []

    for data in direct_results:
        raw_problems += extract_problems(data)

    for entry in browser_traffic:
        resp_data = entry.get("response", {})
        if resp_data and resp_data.get("data"):
            raw_problems += extract_problems(resp_data["data"])

    # De-duplicate
    seen, unique = set(), []
    for p in raw_problems:
        name = str(p.get("name") or "")
        if name and name not in seen:
            seen.add(name)
            unique.append(p)

    print(f"  Unique problems: {len(unique)}")
    normalized = [normalize(p) for p in unique]

    # ── Step 6: Download topos ────────────────────────────────────────────────
    print("\n[6] Downloading topo images…")
    for p in normalized:
        url = p.get("topo_url", "")
        if url and url.startswith("http"):
            ext  = Path(urlparse(url).path).suffix or ".jpg"
            dest = TOPOS_DIR / f"{slug(p['name'])}{ext}"
            if not dest.exists() and download_image(url, dest):
                p["topo_img"] = dest.name
                print(f"  Saved: {dest.name}")

    # ── Save output ───────────────────────────────────────────────────────────
    output = {
        "meta": {
            "scraped_at":      time.strftime("%Y-%m-%dT%H:%M:%S"),
            "lcc_id":          lcc_id,
            "problems_found":  len(normalized),
        },
        "problems": normalized,
        "raw_data": direct_results,
    }
    OUTPUT_FILE.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved: {OUTPUT_FILE.name}")

    if normalized:
        print(f"\n{len(normalized)} problems scraped. Run:  python generate_site.py")
    else:
        print("\nNo problems extracted yet.")
        print(f"Check {QUERIES_FILE.name} to see raw GraphQL traffic.")
        print("Share that file and we'll adjust the parser.")


if __name__ == "__main__":
    run()
