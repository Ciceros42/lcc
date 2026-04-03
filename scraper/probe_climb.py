"""
probe_climb.py — test webClimb(slug) and climb(id) for topo/description fields
"""
import json, os, time, requests
from dotenv import load_dotenv
from pathlib import Path
from playwright.sync_api import sync_playwright, Request

load_dotenv()
TOKEN_FILE  = Path(__file__).parent / "auth_token.txt"
GRAPHQL_URL = "https://kaya-beta.kayaclimb.com/graphql"
LOGIN_URL   = "https://kaya-app.kayaclimb.com/login"
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

def get_token() -> str:
    token = ""
    if TOKEN_FILE.exists():
        try:
            token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["headers"]["authorization"]
        except Exception:
            pass
    if token:
        r = requests.post(GRAPHQL_URL, json={"query": "{ currentUser { id } }"},
                          headers={"Content-Type": "application/json", "Authorization": token,
                                   "User-Agent": "Mozilla/5.0", "Origin": "https://kaya-app.kayaclimb.com"},
                          timeout=10)
        if r.status_code == 200:
            return token
    print("Token expired — logging in…")
    with sync_playwright() as pw:
        iphone = pw.devices["iPhone 14 Pro"]
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(**iphone)
        page = ctx.new_page()
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
        TOKEN_FILE.write_text(json.dumps({"headers": {"authorization": token}}, indent=2), encoding="utf-8")
    return token

token = get_token()
hdrs  = {
    "Content-Type": "application/json", "Authorization": token,
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
    "Origin": "https://kaya-app.kayaclimb.com",
}

# Sample slugs from scraped data
SLUG = "Surfboard-Problem-v4-Little-Cottonwood-Canyon-130746"
ID   = "130746"   # last number in slug

def q(label, query, variables={}):
    print(f"\n--- {label} ---")
    r = requests.post(GRAPHQL_URL, json={"query": query, "variables": variables}, headers=hdrs, timeout=15)
    print(f"HTTP {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2)[:2000])
    except Exception:
        print(r.text[:500])

# 1. webClimb(slug:)
q("webClimb(slug)", f"""
query {{ webClimb(slug: "{SLUG}") {{
    id slug name description
    topo_url photo_url
    rating ascent_count
    grade {{ name }}
    area {{ id name slug }}
    __typename
}} }}
""")

# 2. climb(id:) with known ID
q("climb(id)", f"""
query {{ climb(id: "{ID}") {{
    id slug name description
    topo_url photo_url
    rating ascent_count
    grade {{ name }}
    location {{ id name }}
    __typename
}} }}
""")

# 3. Probe webClimb fields via errors
for field in ["topo_url", "photo_url", "description", "beta",
              "topos", "images", "media", "photos",
              "topo_image_url", "cover_photo_url", "thumbnail_url"]:
    q(f"webClimb.{field}", f"""
        query {{ webClimb(slug: "{SLUG}") {{ id name {field} }} }}
    """)
