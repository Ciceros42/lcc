"""
scrape_details.py
=================
Fetches descriptions and topo/photo URLs for each climb in scraped_data.json
using the Kaya GraphQL API. Run AFTER scrape_kaya_v2.py.

Uses slow pacing (3s between requests) to stay under Cloudflare's rate limit.
Saves progress after every 50 climbs so it can resume if interrupted.

Usage
-----
  python scrape_details.py
"""

import json, os, re, time, urllib.request
from dotenv import load_dotenv
from pathlib import Path
from playwright.sync_api import sync_playwright, Request
import requests as req

load_dotenv()

SCRAPER_DIR  = Path(__file__).parent
ROOT         = SCRAPER_DIR.parent
TOKEN_FILE   = SCRAPER_DIR / "auth_token.txt"
DATA_FILE    = SCRAPER_DIR / "scraped_data.json"
TOPOS_DIR    = ROOT / "images" / "topos"
GRAPHQL_URL  = "https://kaya-beta.kayaclimb.com/graphql"
LOGIN_URL    = "https://kaya-app.kayaclimb.com/login"

EMAIL    = os.getenv("KAYA_EMAIL", "")
PASSWORD = os.getenv("KAYA_PASSWORD", "")

# Delay between API calls (seconds) — keep slow to avoid Cloudflare
REQUEST_DELAY = 3.0
# Save progress every N climbs
SAVE_EVERY    = 50

fresh_headers: dict = {}


# ── Auth ──────────────────────────────────────────────────────────────────────

def on_request(request: Request):
    if GRAPHQL_URL not in request.url:
        return
    try:
        hdrs = dict(request.headers)
        if hdrs.get("authorization"):
            fresh_headers["authorization"] = hdrs["authorization"]
    except Exception:
        pass


def fresh_login() -> str:
    print("Logging in for fresh token…")
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
            r = req.post(GRAPHQL_URL,
                         json={"query": "{ currentUser { id } }"},
                         headers=base_headers(token), timeout=10)
            if r.status_code == 200 and r.json().get("data", {}).get("currentUser"):
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


# ── GraphQL ───────────────────────────────────────────────────────────────────

CLIMB_QUERY = """
query webClimb($slug: String!) {
  webClimb(slug: $slug) {
    id
    slug
    name
    description
    rating
    grade { name }
    area { id name }
    __typename
  }
}
"""

CLIMB_BY_ID_QUERY = """
query climb($id: ID!) {
  climb(id: $id) {
    id
    name
    description
    rating
    photo_url
    photos { url }
    grade { name }
    location { id name }
    __typename
  }
}
"""


def extract_id(slug: str) -> str:
    m = re.search(r"-(\d+)$", slug)
    return m.group(1) if m else ""


def gql_climb(slug: str, token: str) -> dict | None:
    """Try webClimb(slug) then fall back to climb(id). Returns data dict or None."""
    climb_id = extract_id(slug)

    # Try webClimb first
    for query, variables, key in [
        (CLIMB_QUERY,       {"slug": slug},     "webClimb"),
        (CLIMB_BY_ID_QUERY, {"id": climb_id},   "climb"),
    ]:
        try:
            r = req.post(
                GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers=base_headers(token),
                timeout=20,
            )
            if r.status_code == 403:
                raise RuntimeError("Cloudflare 403 — IP blocked, wait before retrying")
            if r.status_code == 200:
                body = r.json()
                data = (body.get("data") or {}).get(key)
                if data:
                    return data
        except RuntimeError:
            raise
        except Exception:
            pass
    return None


def download_image(url: str, dest: Path) -> bool:
    try:
        r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(r, timeout=20) as resp:
            dest.write_bytes(resp.read())
        return True
    except Exception:
        return False


def slug_to_filename(name: str, ext: str = ".jpg") -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") + ext


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    TOPOS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Kaya Detail Scraper — descriptions + topo photos")
    print("=" * 60)

    # Load data
    if not DATA_FILE.exists():
        print(f"ERROR: {DATA_FILE} not found. Run scrape_kaya_v2.py first.")
        return
    data     = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    problems = data["problems"]
    print(f"Loaded {len(problems)} problems from {DATA_FILE.name}")

    # Find problems that still need details
    need_details = [p for p in problems if not p.get("description") and p.get("slug")]
    print(f"Problems needing details: {len(need_details)}")
    if not need_details:
        print("All problems already have details.")
        return

    token = load_token()
    print(f"Token: {token[:40]}…\n")

    # Build lookup by slug for fast updates
    by_slug = {p["slug"]: p for p in problems}

    fetched = 0
    failed  = 0
    photos  = 0

    for i, p in enumerate(need_details):
        slug = p["slug"]
        if i % 10 == 0:
            pct = int(100 * i / len(need_details))
            print(f"[{i}/{len(need_details)} {pct}%] {p['name'][:40]}")

        try:
            detail = gql_climb(slug, token)
            if detail:
                # Update description
                desc = detail.get("description") or ""
                by_slug[slug]["description"] = desc

                # Handle topo/photo URL
                photos_list = detail.get("photos") or []
                topo_url = detail.get("photo_url") or (photos_list[0]["url"] if photos_list else "") or ""
                if topo_url and topo_url.startswith("http"):
                    ext      = Path(topo_url.split("?")[0]).suffix or ".jpg"
                    filename = slug_to_filename(p["name"], ext)
                    dest     = TOPOS_DIR / filename
                    if not dest.exists():
                        if download_image(topo_url, dest):
                            by_slug[slug]["topo_img"] = filename
                            photos += 1
                    else:
                        by_slug[slug]["topo_img"] = filename

                fetched += 1
            else:
                failed += 1

        except RuntimeError as e:
            print(f"\nFATAL: {e}")
            print("Saving progress and stopping. Re-run after the block clears.")
            break
        except Exception as e:
            failed += 1
            if failed % 20 == 0:
                print(f"  [{failed} failures so far] last: {e}")

        # Save progress periodically
        if (i + 1) % SAVE_EVERY == 0:
            data["problems"] = list(by_slug.values())
            DATA_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            print(f"  → Checkpoint saved ({fetched} fetched, {photos} photos, {failed} failed)")

        time.sleep(REQUEST_DELAY)

    # Final save
    data["problems"] = list(by_slug.values())
    DATA_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"Done.  Fetched: {fetched}  Photos: {photos}  Failed: {failed}")
    print(f"Saved: {DATA_FILE.name}")
    print("Next step: python generate_site.py")


if __name__ == "__main__":
    run()
