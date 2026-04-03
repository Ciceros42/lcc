"""
probe_graphql.py
================
Sends minimal GraphQL queries to kaya-beta.kayaclimb.com/graphql and prints
the full responses including error messages. GraphQL errors tell us exactly
what field names exist — we use them to discover the right query format.

Usage
-----
  python probe_graphql.py
"""

import json
import os
import time
from dotenv import load_dotenv
from pathlib import Path
from playwright.sync_api import sync_playwright, Request
import requests

load_dotenv()

TOKEN_FILE  = Path(__file__).parent / "auth_token.txt"
GRAPHQL_URL = "https://kaya-beta.kayaclimb.com/graphql"
LOGIN_URL   = "https://kaya-app.kayaclimb.com/login"
LCC_ID      = "6146"

EMAIL    = os.getenv("KAYA_EMAIL", "")
PASSWORD = os.getenv("KAYA_PASSWORD", "")

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
    """Open browser, log in, capture and return a fresh token."""
    print("Token expired or missing — logging in to get a fresh one…")
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
        time.sleep(6)
        browser.close()
    token = fresh_headers.get("authorization", "")
    if token:
        saved = {"headers": {"authorization": token}}
        TOKEN_FILE.write_text(json.dumps(saved, indent=2), encoding="utf-8")
        print(f"  Fresh token saved.")
    return token

# ── Load token ────────────────────────────────────────────────────────────────

def load_token() -> str:
    token = ""
    if TOKEN_FILE.exists():
        try:
            data  = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            token = data.get("headers", {}).get("authorization", "")
        except Exception:
            pass

    # Quick check — if token exists, test it
    if token:
        hdrs = {"Content-Type": "application/json", "Authorization": token,
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
                "Origin": "https://kaya-app.kayaclimb.com"}
        try:
            resp = requests.post(GRAPHQL_URL,
                                 json={"query": "{ currentUser { id } }"},
                                 headers=hdrs, timeout=10)
            if resp.status_code == 200:
                print("  Saved token is still valid.")
                return token
        except Exception:
            pass

    # Token missing or expired — re-login
    return fresh_login()


def base_headers(token: str) -> dict:
    return {
        "Content-Type":  "application/json",
        "Authorization": token,
        "User-Agent":    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        "Origin":        "https://kaya-app.kayaclimb.com",
        "Referer":       "https://kaya-app.kayaclimb.com/",
    }


# ── Send a query and print FULL response ─────────────────────────────────────

def probe(label: str, query: str, variables: dict, token: str):
    print(f"\n{'─'*50}")
    print(f"QUERY: {label}")
    hdrs = base_headers(token)
    try:
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=hdrs,
            timeout=15,
        )
        print(f"HTTP {resp.status_code}")
        try:
            body = resp.json()
            print(json.dumps(body, indent=2)[:1500])   # print up to 1500 chars
        except Exception:
            print(resp.text[:500])
    except Exception as e:
        print(f"Request failed: {e}")


def run():
    token = load_token()
    print(f"Using token: {token[:40]}…")
    print("Probing Kaya GraphQL schema — reading error messages to find field names\n")

    # ── 1. Confirm auth works ─────────────────────────────────────────────────
    probe("currentUser (known-good)", """
        query { currentUser { id email __typename } }
    """, {}, token)

    # ── 2. Bare typename — always works on any GraphQL server ─────────────────
    probe("__typename", "{ __typename }", {}, token)

    # ── 3. Try root-level field names ─────────────────────────────────────────
    for field in ["location", "locations", "area", "areas", "guide", "guides",
                  "sector", "sectors", "crag", "crags", "zone", "zones",
                  "boulder", "boulders", "problem", "problems"]:
        probe(f"root field: {field}", f"{{ {field} {{ id }} }}", {}, token)

    # ── 4. Try location with int ID ───────────────────────────────────────────
    probe("location(id: Int)", f"""
        query {{ location(id: {LCC_ID}) {{ id name __typename }} }}
    """, {}, token)

    # ── 5. Try location with string ID ────────────────────────────────────────
    probe('location(id: String)', f"""
        query {{ location(id: "{LCC_ID}") {{ id name __typename }} }}
    """, {}, token)

    # ── 6. Try with variable ──────────────────────────────────────────────────
    probe("location(id: variable Int)", """
        query GetLocation($id: Int!) { location(id: $id) { id name __typename } }
    """, {"id": int(LCC_ID)}, token)

    probe("location(id: variable ID)", """
        query GetLocation($id: ID!) { location(id: $id) { id name __typename } }
    """, {"id": LCC_ID}, token)

    # ── 7. Try introspection now that we have a working token ────────────────
    probe("introspection: Query fields", """
        { __schema { queryType { fields { name args { name type { name kind } } } } } }
    """, {}, token)

    # ── 8. Explore Location type fields ──────────────────────────────────────
    print("\n\n=== PHASE 2: Exploring Location type fields ===")

    # Basic scalar fields
    for field in ["description", "lat", "lng", "access", "parking",
                  "cover_photo_url", "image_url", "rock_type", "discipline",
                  "problem_count", "route_count", "elevation"]:
        probe(f"Location.{field}", f"""
            query {{ location(id: "{LCC_ID}") {{ id name {field} }} }}
        """, {}, token)

    # Child/sub-area fields
    for field in ["children", "sub_locations", "sub_areas", "subareas",
                  "sectors", "walls", "zones", "areas", "locations"]:
        probe(f"Location.{field}", f"""
            query {{ location(id: "{LCC_ID}") {{ id name {field} {{ id name __typename }} }} }}
        """, {}, token)

    # Problem fields directly on location
    for field in ["problems", "routes", "climbs", "boulders", "boulder_problems"]:
        probe(f"Location.{field}", f"""
            query {{ location(id: "{LCC_ID}") {{ id name {field} {{ id name __typename }} }} }}
        """, {}, token)

    # ── 9. More Location fields based on error hints ─────────────────────────
    print("\n\n=== PHASE 3: webLocation, child queries, route queries ===")

    # Fields we know exist from error hints
    for field in ["boulder_count", "climb_count", "follower_count",
                  "photo_url", "lco_photo_url", "slug",
                  "latitude", "longitude", "coords", "location_type",
                  "parent_id", "parent", "childLocations", "child_locations",
                  "type", "tags", "disciplines"]:
        probe(f"Location.{field}", f"""
            query {{ location(id: "{LCC_ID}") {{ id name {field} }} }}
        """, {}, token)

    # webLocation query — different entry point, might include children
    probe("webLocation(id)", f"""
        query {{ webLocation(id: "{LCC_ID}") {{ id name __typename }} }}
    """, {}, token)

    probe("webLocation with children", f"""
        query {{ webLocation(id: "{LCC_ID}") {{
            id name description
            childLocations {{ id name __typename }}
        }} }}
    """, {}, token)

    # Root-level queries for routes/climbs with location filter
    for q in ["route", "routes", "climb", "climbs", "boulder", "boulders"]:
        probe(f"root {q}(location_id)", f"""
            query {{ {q}(location_id: "{LCC_ID}") {{ id name __typename }} }}
        """, {}, token)
        probe(f"root {q}(locationId)", f"""
            query {{ {q}(locationId: "{LCC_ID}") {{ id name __typename }} }}
        """, {}, token)

    # Try locations query with parent filter
    probe("location with parent filter", f"""
        query {{ location(parent_id: "{LCC_ID}") {{ id name __typename }} }}
    """, {}, token)

    # locationType query
    probe("locationType", f"""
        query {{ locationType {{ id name __typename }} }}
    """, {}, token)

    # ── PHASE 4: climblist, webLocation(slug), climb fields ──────────────────
    print("\n\n=== PHASE 4: climblist, webLocation, climb, location_type ===")

    LCC_SLUG = "Little-Cottonwood-Canyon-986245"

    # webLocation with slug
    probe("webLocation(slug)", f"""
        query {{ webLocation(slug: "{LCC_SLUG}") {{ id name __typename }} }}
    """, {}, token)

    # Explore WebLocation fields
    for field in ["description", "latitude", "longitude", "photo_url",
                  "locations", "climbs", "children", "location", "areas",
                  "child_locations", "sub_locations", "boulder_count", "climb_count"]:
        probe(f"WebLocation.{field}", f"""
            query {{ webLocation(slug: "{LCC_SLUG}") {{ id name {field} }} }}
        """, {}, token)

    probe("WebLocation.location { id name }", f"""
        query {{ webLocation(slug: "{LCC_SLUG}") {{
            id name
            location {{ id name boulder_count __typename }}
        }} }}
    """, {}, token)

    # climblist — try different argument patterns
    for arg in [f'location_id: "{LCC_ID}"', f'locationId: "{LCC_ID}"',
                f'id: "{LCC_ID}"', f'location: "{LCC_ID}"',
                f'location_id: {LCC_ID}', f'locationId: {LCC_ID}']:
        probe(f"climblist({arg})", f"""
            query {{ climblist({arg}) {{ id name __typename }} }}
        """, {}, token)

    # climblist with no args — maybe it lists all?
    probe("climblist (no args)", """
        query { climblist { id name __typename } }
    """, {}, token)

    # climb fields exploration
    probe("climb — what args does it take?", """
        query { climb { id name __typename } }
    """, {}, token)

    # location_type sub-fields
    probe("Location.location_type { id name }", f"""
        query {{ location(id: "{LCC_ID}") {{
            id name
            location_type {{ id name __typename }}
        }} }}
    """, {}, token)

    # parent_location
    probe("Location.parent_location", f"""
        query {{ location(id: "{LCC_ID}") {{
            id name
            parent_location {{ id name __typename }}
        }} }}
    """, {}, token)

    # post query (suggested when trying route)
    probe("post(id)", f"""
        query {{ post(id: "{LCC_ID}") {{ id __typename }} }}
    """, {}, token)

    # ── PHASE 5: Climblist fields, WebLocation remaining fields, ID range scan ─
    print("\n\n=== PHASE 5: Climblist fields, WebLocation extras, ID range ===")

    LCC_SLUG = "Little-Cottonwood-Canyon-986245"

    # WebLocation fields suggested by error hints or common naming
    for field in ["lco_bio", "slug", "lco_photo_url", "route_count",
                  "follower_count", "parent_location"]:
        probe(f"WebLocation.{field}", f"""
            query {{ webLocation(slug: "{LCC_SLUG}") {{ id name {field} }} }}
        """, {}, token)

    probe("WebLocation.parent_location { id name }", f"""
        query {{ webLocation(slug: "{LCC_SLUG}") {{
            id name
            parent_location {{ id name __typename }}
        }} }}
    """, {}, token)

    # Explore Climblist type fields — ID 6146 = "Tahoe" climblist but reveals type shape
    for field in ["climbs", "items", "location", "problems", "routes",
                  "description", "slug", "user"]:
        probe(f"Climblist.{field}", f"""
            query {{ climblist(id: "6146") {{ id name {field} {{ id name __typename }} }} }}
        """, {}, token)

    # locationType(id: "2") — LCC is type 2 "Destination"
    probe("locationType(id: 2)", """
        query { locationType(id: "2") { id name __typename } }
    """, {}, token)

    # Try locationType with sub-fields
    for field in ["locations", "description", "slug"]:
        probe(f"LocationType.{field}", """
            query { locationType(id: "2") { id name """ + field + """ { id name __typename } } }
        """, {}, token)

    # Scan IDs near 6146 — LCC sub-areas likely have IDs in the same namespace
    # Try a range to find child locations
    print("\n--- Scanning nearby IDs for LCC sub-areas ---")
    candidate_ids = list(range(6140, 6160)) + [239, 240, 241]  # also try US children
    for loc_id in candidate_ids:
        probe(f"location(id: {loc_id})", f"""
            query {{ location(id: "{loc_id}") {{
                id name
                parent_location {{ id name }}
                location_type {{ id name }}
            }} }}
        """, {}, token)

    # Also try the webLocation's climblist or climb sub-fields
    for field in ["climblist", "climblist_id", "climb_list", "guide", "guides",
                  "web_locations", "sub_web_locations", "child_web_locations",
                  "nearby_locations", "nearby"]:
        probe(f"WebLocation.{field}", f"""
            query {{ webLocation(slug: "{LCC_SLUG}") {{ id name {field} {{ id name __typename }} }} }}
        """, {}, token)

    print(f"\n{'='*50}")
    print("DONE — climblist and webLocation are the key leads.")


if __name__ == "__main__":
    run()
