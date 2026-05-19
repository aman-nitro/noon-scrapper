from loguru import logger

from proxy.proxy_client import ProxyClient, ProxyHTTPError
from proxy.proxy_manager import ProxyManager, ProxyConfig, InMemoryStorage
from proxy.proxies import proxy_urls
from constants import NOON_BASE_URL

NOON_CATEGORY_ENDPOINT = NOON_BASE_URL + "/category"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache, max-age=0, must-revalidate, no-store",
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
    "x-ecom-zonecode": "AE_DXB-S14",
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
    manager = ProxyManager(config=config, storage_backend=storage, platform="noon")

    all_proxy_urls = []
    for _, urls in proxy_urls.items():
        if isinstance(urls, list):
            all_proxy_urls.extend(urls)

    loaded = manager.load_proxies_from_url_list(all_proxy_urls)
    logger.info(f"[PROXY] Loaded {loaded} proxies")

    client = ProxyClient(config=manager.config, proxy_manager=manager)
    return manager, client, loaded


class NoonCategoryScraper:

    def __init__(self, ecom_node: str = "AE_DXB-S14"):
        self.proxy_manager, self.proxy_client, self.proxy_count = build_proxy_manager()
        self.ecom_node = ecom_node

    async def fetch_categories(self) -> list[dict] | None:
        try:
            response = await self.proxy_client.get(NOON_CATEGORY_ENDPOINT, headers=HEADERS)
            logger.info(f"[HTTP {response.status_code}]")

            if response.status_code == 200:
                return response.json()

            logger.error(f"[FAILED] status={response.status_code}")
            return None

        except ProxyHTTPError as e:
            logger.error(f"[PROXY ERROR] {e}")
            return None

        except Exception as e:
            logger.error(f"[ERROR] {e}")
            return None

    def flatten_categories(self, categories: list[dict], parent_code: str | None = None) -> list[dict]:
        result = []
        for cat in categories:
            flat = {
                "id": cat.get("id_category"),
                "parent_id": cat.get("id_category_parent"),
                "code": cat.get("code"),
                "name": cat.get("name"),
            }
            result.append(flat)
            children = cat.get("children", [])
            if children:
                result.extend(self.flatten_categories(children))
        return result

    async def scrape(self) -> list[dict]:
        logger.info("Fetching category tree...")
        data = await self.fetch_categories()

        if data is None:
            logger.error("Failed to fetch categories.")
            return []

        categories = None
        facets = data.get('facets', []) 
        for facet in facets:
            if facet.get('code') == "category":
                categories = facet

        if categories and categories.get('data', []):
            flat = self.flatten_categories(categories.get('data', []))
            logger.info(f"Total categories found: {len(flat)}")
            return flat