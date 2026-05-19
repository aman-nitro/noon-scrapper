import asyncio

from loguru import logger

from proxy.proxy_client import ProxyClient
from proxy.proxy_manager import ProxyManager, ProxyConfig, InMemoryStorage
from proxy.proxies import proxy_urls

from constants import NOON_BASE_URL

PAGE_LIMIT = 100
MAX_PAGES_CONCURRENT = 10

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache",
    "priority": "u=1, i",
    "referer": "https://www.noon.com/uae-en/",
    "sec-ch-ua": '"Chromium";v="148", "Brave";v="148"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
    "x-border-enabled": "true",
    "x-cms": "v2",
    "x-content": "desktop",
    "x-ecom-zonecode": "AE_DXB-S14", # this will be dynamic
}


def build_proxy_manager():
    config = ProxyConfig()
    config.timeout = 25.0
    config.proxy_cooldown_on_429 = 15.0
    config.cooldown_on_403 = 30.0
    config.proxy_cooldown_on_timeout = 15.0
    config.cooldown_on_5xx = 10.0
    config.proxy_cooldown_on_connection_error = 30.0
    config.default_cooldown = 15.0
    config.max_attempts_per_request = 4
    config.progressive_failure_threshold = 2
    config.reservation_ttl = 30.0
    config.cooldown_on_407 = 120.0

    storage = InMemoryStorage()
    manager = ProxyManager(config=config, storage_backend=storage, platform="noon")

    all_proxy_urls = []
    for _, urls in proxy_urls.items():
        if isinstance(urls, list):
            all_proxy_urls.extend(urls)

    loaded = manager.load_proxies_from_url_list(all_proxy_urls)
    logger.info(f"[PROXY] Loaded {loaded} proxies")

    return manager


class NoonProductScraper:

    def __init__(self, ecom_node: str = "AE_DXB-S14"):
        proxy_manager = build_proxy_manager()
        self.proxy_client = ProxyClient(config=proxy_manager.config,proxy_manager=proxy_manager)
        self.ecom_node = ecom_node

    async def fetch_page(self, category: str, page: int) -> dict | None:
        url = f"{NOON_BASE_URL}/{category}"
        try:
            HEADERS["x-ecom-zonecode"] = self.ecom_node
            response = await self.proxy_client.get(
                url,
                headers=HEADERS,
                params={"page": page, "limit": PAGE_LIMIT},
            )
            logger.info(f"[HTTP {response.status_code}]")
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"[ERROR] {e}")
            return None

    async def scrape_category(self, category: str) -> list[dict]:
        first = await self.fetch_page(category, 1)
        if not first:
            return []

        nb_pages = first.get("nbPages", 1)
        all_hits = first.get("hits", [])

        if nb_pages > 1:
            sem = asyncio.Semaphore(MAX_PAGES_CONCURRENT)

            async def fetch_more(page):
                async with sem:
                    return await self.fetch_page(category, page)

            results = await asyncio.gather(
                *[fetch_more(p) for p in range(2, nb_pages + 1)],
                return_exceptions=True,
            )

            for r in results:
                if isinstance(r, dict):
                    all_hits.extend(r.get("hits", []))

        return all_hits

    async def scrape(self, category: str) -> list[dict]:
        all_products = await self.scrape_category(category)
        return all_products