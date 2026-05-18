#This script scrapes the product catalog of noon.com starting from a given category, and saves results in batches of 10k products.
#It doesn't run concurrenly, but it can be easily modified to do so by using asyncio and aiohttp for making requests, and aiofiles for writing output files asynchronously.
import requests
import json
import time
import os
from collections import deque


BASE_URL  = "https://www.noon.com/_vs/nc/mp-customer-catalog-api/api/v3/u/"
START_CAT = "hajj-health-essentials"

# Paste your fresh cookie here when the old one expires
COOKIE = "ak_bmsc=6449A2C31E0F07EA67C1E40E9592DE6B~000000000000000000000000000000~YAAQlvQ3F1SE6R6eAQAAXL8lJR+an8wDaLSxpy4phglrZeO/+RCpdqeYXrsfWjT3DkXIZJ1yxIejvV3ZhoeekN1We5Xnofh54rm3fcC0OUHvGWueJyU6980R3oo3U7W1+UTzOPt9Y6S7KgQKXGNZyTzdKYEJXdZcuMoyVkPUJYyO38P8V5ygGNze/HFpr8sqBQhQVYd3KzP/ypVrn5ovgnQLyZY//gLOyQNJ8jZsGjsw2dD+1U+JwaErVgViXTh/2843X6dx+VN34g0bmFHUM34b8TPHLxyqRO+cLK7yzKXPumqqXRTwaaroXo5dwVNWDscOyUrDV/FjlF9MyCbEbzUWuaDA6qSjuoQs; bm_sv=D5444030DA6C36CAD3BFE42C7A512F96~YAAQlvQ3F9i27R6eAQAAnTE8JR8ZPCNEnKTs32U3oRFYI4ZuCcz79NNnvRteFsCg5mWH5MTdx95y9ARNVDbU8x0xmeA+QYZvHQOe3Rlrfv81Zb7XXT0PxLyINuyPpcou+FH3hJa4F07KRqo61nVevpOIVz/9GRf2dpIdu3DDU6GWHHHike47auge9axthptVpbG5Ik9o6NM1Gwxudzuy70tnqdVzOUeO9F9ZxcQ9/ETb+adlYcFXcuaM0UXHX1k=~1; dcae=1; nguestv2=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJraWQiOiI3OWU4MGQ2NDQ2ZDc0OTVjODJjMjQ0NTA4MmU3OGIzZiIsImlhdCI6MTc3ODczOTY5MSwiZXhwIjoxNzc4NzM5OTkxfQ.eIOK3lvCwDJQ0Hx0xaCjQ2_e_QvcjMMEM9I9ahmL6gw; x-available-ae=ecom; x-location-ecom-ae=eyJsYXQiOiAyNTIxMTY0MDMsICJsbmciOiA1NTI3MDYwNDksICJhcmVhIjogIkFsIFNhdHdhIiwgImlkX2NpdHkiOiAxfQ"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache, max-age=0, must-revalidate, no-store",
    "priority": "u=1, i",
    "referer": "https://www.noon.com/uae-en/",
    "sec-ch-ua": '"Chromium";v="148", "Brave";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sec-gpc": "1",
    "user-agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),

    # Noon required headers
    "x-border-enabled": "true",
    "x-cms": "v2",
    "x-content": "desktop",
    "x-ecom-zonecode": "AE_DXB-S14",
    # "x-lat": "252116403",
    # "x-lng": "552706049",
    "x-locale": "en-ae",
    "x-mp-country": "ae",
    "x-platform": "web",
    # "x-rocket-enabled": "true",
    # "x-rocket-zonecode": "W00068765A",
    "x-visitor-id": "d7adf681-747a-4c96-bfbb-b19ed13f4280",

    # IMPORTANT
    "Cookie": COOKIE,
}

OUTPUT_FILE = "products.jsonl"
STATE_FILE  = "scraper_state.json"
DELAY       = 0.6   # seconds between requests (be polite)
PAGE_LIMIT  = 50    # noon's default page size

# ─────────────────────────── HELPERS ─────────────────────────────────────────

def fetch_page(category_code: str, page: int = 1) -> dict | None:
    """Hit the API for a single category + page. Returns parsed JSON or None."""
    url = BASE_URL + category_code
    params = {"page": page, "limit": PAGE_LIMIT}
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=20)
        print("noor api giving:", r.status_code)

        if r.status_code == 200:
            # print(r.json())
            return r.json()
        
        print(f"  [HTTP {r.status_code}] {category_code} p={page}")
        return None
    except Exception as e:
        print(f"  [ERROR] {category_code} p={page} → {e}")
        return None


def extract_category_codes(data: dict) -> list[str]:
    """
    Walk the nested 'category' facet tree and return every code found
    (both intermediate nodes and leaves).
    """
    codes = []
    for facet in data.get("facets", []):
        if facet.get("code") == "category":
            for root_node in facet.get("data", []):
                _walk_tree(root_node, codes)
    return codes


def _walk_tree(node: dict, out: list):
    """Recursive DFS over category tree nodes."""
    code = node.get("code", "")
    if code:
        out.append(code)
    for child in node.get("children", []):
        _walk_tree(child, out)


def save_products(hits: list, category_code: str):
    """Append hits to the JSONL output file."""
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for hit in hits:
            hit["_scraped_from_category"] = category_code
            f.write(json.dumps(hit, ensure_ascii=False) + "\n")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "visited_categories": [],
        "queue": [START_CAT],
        "total_products": 0,
    }


def save_state(visited: set, queue: deque, total: int):
    with open(STATE_FILE, "w") as f:
        json.dump({
            "visited_categories": list(visited),
            "queue": list(queue),
            "total_products": total,
        }, f)


# ─────────────────────────── MAIN CRAWL ──────────────────────────────────────

def crawl():
    state   = load_state()
    visited = set(state["visited_categories"])
    queue   = deque(state["queue"])
    total   = state["total_products"]

    print(f"▶  Crawl started")
    print(f"   Queue  : {len(queue)} categories pending")
    print(f"   Visited: {len(visited)} categories done")
    print(f"   Products saved so far: {total}")
    print()

    try:
        while queue:
            cat_code = queue.popleft()

            if cat_code in visited:
                continue

            print(f"── {cat_code}")

            # ── Fetch page 1 ──────────────────────────────────────────────
            data = fetch_page(cat_code, page=1)
            if data is None:
                visited.add(cat_code)
                save_state(visited, queue, total)
                continue

            # ── Discover child categories ─────────────────────────────────
            child_codes = extract_category_codes(data)
            new_cats = 0
            for code in child_codes:
                if code not in visited and code not in queue:
                    queue.append(code)
                    new_cats += 1
            if new_cats:
                print(f"   ↳ {new_cats} new child categories queued")

            # ── Save page-1 products ──────────────────────────────────────
            hits     = data.get("hits", [])
            nb_pages = data.get("nbPages", 1)
            nb_hits  = data.get("nbHits", 0)
            save_products(hits, cat_code)
            total += len(hits)
            print(f"   hits={nb_hits}  pages={nb_pages}  p1_items={len(hits)}  running={total}")

            # ── Paginate remaining pages ──────────────────────────────────
            for page in range(2, nb_pages + 1):
                time.sleep(DELAY)
                pdata = fetch_page(cat_code, page=page)
                if pdata is None:
                    break
                phits = pdata.get("hits", [])
                save_products(phits, cat_code)
                total += len(phits)
                print(f"   page {page:>4}/{nb_pages}  +{len(phits)}  running={total}")

            # ── Mark done & checkpoint ────────────────────────────────────
            visited.add(cat_code)
            save_state(visited, queue, total)
            time.sleep(DELAY)

    except KeyboardInterrupt:
        print("\n⚠  Interrupted – state saved. Re-run to resume.")
        save_state(visited, queue, total)

    print(f"\n✅  Crawl complete.")
    print(f"   Total products : {total}")
    print(f"   Categories done: {len(visited)}")
    print(f"   Output file    : {OUTPUT_FILE}")


if __name__ == "__main__":
    crawl()