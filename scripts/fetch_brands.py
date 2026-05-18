import asyncio
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from proxy.proxy_client import ProxyClient, ProxyHTTPError
from proxy.proxy_manager import ProxyManager, ProxyConfig, InMemoryStorage
from proxy.proxies import proxy_urls

# ───────────────────────── CONFIG ─────────────────────────

BASE_URL = (
    "https://www.noon.com/_vs/nc/mp-customer-catalog-api"
    "/api/v3/u/brands/paginated/category/"
)

LIMIT = 1000
OUTPUT_CSV = "noon_brands.csv"
OUTPUT_JSON = "noon_brands.json"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache, max-age=0, must-revalidate, no-store",
    "priority": "u=1, i",
    "referer": "https://www.noon.com/uae-en/category/",
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
    "x-ecom-zonecode": "AE_DXB-S14",
    # Uncomment and set your cookie when needed:
    # "Cookie": "YOUR_COOKIE_HERE",
}


# ───────────────────────── PROXY SETUP ─────────────────────────


def build_proxy_manager() -> tuple[ProxyManager, ProxyClient, int]:
    config = ProxyConfig()
    config.timeout = 25.0

    config.proxy_cooldown_on_429 = 15.0
    config.cooldown_on_403 = 30.0
    config.proxy_cooldown_on_timeout = 15.0
    config.cooldown_on_5xx = 10.0
    config.proxy_cooldown_on_connection_error = 30.0
    config.default_cooldown = 15.0
    config.cooldown_on_407 = 120.0

    config.max_attempts_per_request = 4
    config.progressive_failure_threshold = 2
    config.reservation_ttl = 30.0

    storage = InMemoryStorage()
    manager = ProxyManager(
        config=config,
        storage_backend=storage,
        platform="noon",
    )

    all_proxy_urls = []
    for _, urls in proxy_urls.items():
        if isinstance(urls, list):
            all_proxy_urls.extend(urls)

    loaded = manager.load_proxies_from_url_list(all_proxy_urls)
    print(f"[PROXY] Loaded {loaded} proxies")

    client = ProxyClient(
        config=manager.config,
        proxy_manager=manager,
    )

    return manager, client, loaded


# ───────────────────────── SCRAPER ─────────────────────────


class NoonBrandScraper:

    def __init__(self):
        self.proxy_manager, self.proxy_client, self.proxy_count = (
            build_proxy_manager()
        )
        self.stats = {
            "pages_fetched": 0,
            "pages_failed": 0,
            "start_time": time.time(),
        }

    # ───────────────────────── FETCH ─────────────────────────

    async def fetch_page(self, page: int) -> dict | None:
        params = {
            "b[page]": page,
            "b[limit]": LIMIT,
        }
        try:
            response = await self.proxy_client.get(
                BASE_URL,
                headers=HEADERS,
                params=params,
            )
            print(f"[HTTP {response.status_code}] page={page}")

            if response.status_code == 200:
                self.stats["pages_fetched"] += 1
                return response.json()

            self.stats["pages_failed"] += 1
            return None

        except ProxyHTTPError as e:
            msg = str(e)
            if "407" in msg:
                print(f"[PROXY AUTH ERROR] page={page}")
            else:
                print(f"[PROXY ERROR] page={page} → {e}")
            self.stats["pages_failed"] += 1
            return None

        except Exception as e:
            print(f"[ERROR] page={page} → {e}")
            self.stats["pages_failed"] += 1
            return None

    # ───────────────────────── COLLECT ─────────────────────────

    async def fetch_all_brands(self) -> list[dict]:
        all_brands: list[dict] = []
        page = 1

        print("Starting brand fetch...")

        while True:
            print(f"  Fetching page {page}...", end=" ", flush=True)

            data = await self.fetch_page(page)

            if data is None:
                print("FAILED — stopping early.")
                break

            brands_on_page = (
                data.get("selectedBrands", [])
                + data.get("popularBrands", [])
                + data.get("regularBrands", [])
            )

            all_brands.extend(brands_on_page)
            print(
                f"got {len(brands_on_page)} brands "
                f"(total so far: {len(all_brands)})"
            )

            is_last = data.get("brandFilters", {}).get("lastPage", True)
            if is_last:
                print("Reached last page.")
                break

            page += 1
            await asyncio.sleep(0.3)

        return all_brands

    # ───────────────────────── DEDUP ─────────────────────────

    @staticmethod
    def deduplicate(brands: list[dict]) -> list[dict]:
        seen: set[str] = set()
        unique: list[dict] = []
        for brand in brands:
            key = brand.get("code") or brand.get("name") or str(brand)
            if key not in seen:
                seen.add(key)
                unique.append(brand)
        return unique

    # ───────────────────────── SAVE ─────────────────────────

    @staticmethod
    def save_json(brands: list[dict], path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(brands, f, ensure_ascii=False, indent=2)
        print(f"[SAVE] JSON → {path}")

    @staticmethod
    def save_csv(brands: list[dict], path: str) -> None:
        if not brands:
            print("[SAVE] No brands to write to CSV.")
            return

        # Collect all keys across all brand dicts for dynamic columns
        fieldnames = list(
            dict.fromkeys(k for brand in brands for k in brand.keys())
        )

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(brands)

        print(f"[SAVE] CSV  → {path}")

    # ───────────────────────── RUN ─────────────────────────

    async def run(self) -> None:
        try:
            raw_brands = await self.fetch_all_brands()
            unique_brands = self.deduplicate(raw_brands)

            print(f"\nTotal unique brands: {len(unique_brands)}")

            self.save_json(unique_brands, OUTPUT_JSON)
            # self.save_csv(unique_brands, OUTPUT_CSV)

        finally:
            await self.proxy_client.close_all_sessions()

            elapsed = time.time() - self.stats["start_time"]
            print("\n══════════════════════════════")
            print("BRAND FETCH COMPLETE")
            print(f"pages_ok={self.stats['pages_fetched']}")
            print(f"pages_fail={self.stats['pages_failed']}")
            print(f"elapsed={elapsed:.1f}s")
            print("══════════════════════════════")


# ───────────────────────── ENTRY ─────────────────────────

if __name__ == "__main__":
    try:
        asyncio.run(NoonBrandScraper().run())
    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")