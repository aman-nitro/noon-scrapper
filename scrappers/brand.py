import asyncio
import time
from loguru import logger

from proxy.proxy_client import ProxyClient, ProxyHTTPError
from proxy.proxy_manager import ProxyManager, ProxyConfig, InMemoryStorage
from proxy.proxies import proxy_urls
from constants import NOON_BASE_URL

NOON_BRAND_ENDPOINT = NOON_BASE_URL +  "/brands/paginated/category/"
LIMIT = 1000

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
    "x-ecom-zonecode": "AE_DXB-S14" # This will be dynamic
}



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
    logger.info(f"[PROXY] Loaded {loaded} proxies")

    client = ProxyClient(
        config=manager.config,
        proxy_manager=manager,
    )

    return manager, client, loaded


class NoonBrandScraper:

    def __init__(self, ecom_node: str = "AE_DXB-S14"):
        self.ecom_node = ecom_node
        self.proxy_manager, self.proxy_client, self.proxy_count = build_proxy_manager()
        self.stats = {
            "pages_fetched": 0,
            "pages_failed": 0,
            "start_time": time.time(),
        }

    async def fetch_page(self, page: int) -> dict | None:
        params = {
            "b[page]": page,
            "b[limit]": LIMIT,
        }
        try:
            HEADERS["x-ecom-zonecode"] = self.ecom_node
            response = await self.proxy_client.get(
                NOON_BRAND_ENDPOINT,
                headers=HEADERS,
                params=params,
            )
            logger.info(f"[HTTP {response.status_code}] page={page}")

            if response.status_code == 200:
                self.stats["pages_fetched"] += 1
                return response.json()

            self.stats["pages_failed"] += 1
            return None

        except ProxyHTTPError as e:
            msg = str(e)
            if "407" in msg:
                logger.error(f"[PROXY AUTH ERROR] page={page}")
            else:
                logger.error(f"[PROXY ERROR] page={page} → {e}")
            self.stats["pages_failed"] += 1
            return None

        except Exception as e:
            logger.error(f"[ERROR] page={page} → {e}")
            self.stats["pages_failed"] += 1
            return None

    async def fetch_all_brands(self) -> list[dict]:
        all_brands: list[dict] = []
        page = 1

        logger.info("Starting brand fetch...")

        while True:
            logger.info(f"  Fetching page {page}...", end=" ", flush=True)

            data = await self.fetch_page(page)

            if data is None:
                logger.error("FAILED — stopping early.")
                break

            brands_on_page = (
                data.get("selectedBrands", [])
                + data.get("popularBrands", [])
                + data.get("regularBrands", [])
            )

            all_brands.extend(brands_on_page)
            logger.info(
                f"got {len(brands_on_page)} brands "
                f"(total so far: {len(all_brands)})"
            )

            is_last = data.get("brandFilters", {}).get("lastPage", True)
            if is_last:
                logger.info("Reached last page.")
                break

            page += 1
            await asyncio.sleep(0.3)

        return all_brands


    @staticmethod
    def deduplicate(brands: list[dict]) -> list[dict]:
        seen: set[str] = set()
        unique: list[dict] = []
        for brand in brands:
            key = brand.get('name')
            if key not in seen:
                seen.add(key)
                unique.append(key)
        return unique