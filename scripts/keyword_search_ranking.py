# import asyncio
# import json
# import time
# from datetime import datetime
# from typing import Dict, List, Optional
# import aiofiles
# import os
# import sys
# import random

# sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)) + "/..")

# from proxy.proxy_manager import ProxyManager, ProxyConfig, InMemoryStorage
# from proxy.proxy_client import ProxyClient
# from proxy.proxies import proxy_urls  # Import your proxy URLs

# BASE_SEARCH_URL = "https://www.noon.com/_vs/nc/mp-customer-catalog-api/api/v3/u/search"

# HEADERS = {
#     "accept": "application/json, text/plain, */*",
#     "accept-language": "en-US,en;q=0.9",
#     "cache-control": "no-cache, max-age=0, must-revalidate, no-store",
#     "pragma": "no-cache",
#     "priority": "u=1, i",
#     "referer": "https://www.noon.com/uae-en/",
#     "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148"',
#     "sec-ch-ua-mobile": "?0",
#     "sec-ch-ua-platform": '"macOS"',
#     "sec-fetch-dest": "empty",
#     "sec-fetch-mode": "cors",
#     "sec-fetch-site": "same-origin",
#     "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
#     "x-border-enabled": "true",
#     "x-cms": "v2",
#     "x-content": "desktop",
#     "x-ecom-zonecode": "AE_DXB-S3",
#     "x-locale": "en-ae",
#     "x-mp-country": "ae",
#     "x-platform": "web",
# }

# OUTPUT_DIR = "keyword_rankings"
# RESULTS_FILE = os.path.join(OUTPUT_DIR, "rankings.jsonl")


# def build_proxy_manager():
#     """Build and configure proxy manager with proxies from proxy_urls."""
#     config = ProxyConfig()
#     config.timeout = 30.0
#     config.proxy_cooldown_on_429 = 15.0
#     config.cooldown_on_403 = 30.0
#     config.proxy_cooldown_on_timeout = 15.0
#     config.cooldown_on_5xx = 10.0
#     config.default_cooldown = 15.0
#     config.max_attempts_per_request = 4
#     config.progressive_failure_threshold = 2

#     storage = InMemoryStorage()
#     manager = ProxyManager(
#         config=config,
#         storage_backend=storage,
#         platform="noon"
#     )

#     # Load proxies from proxy_urls
#     all_proxy_urls = []
#     for key, urls in proxy_urls.items():
#         if isinstance(urls, list):
#             all_proxy_urls.extend(urls)

#     loaded = manager.load_proxies_from_url_list(all_proxy_urls)
#     print(f"[PROXY] Loaded {loaded} proxies")

#     return manager


# class KeywordSearchRanker:
#     """Track keyword search rankings for products."""

#     def __init__(self):
#         os.makedirs(OUTPUT_DIR, exist_ok=True)
        
#         # Build proxy manager with proxies loaded
#         self.proxy_manager = build_proxy_manager()
#         self.proxy_client = ProxyClient(proxy_manager=self.proxy_manager)

#     async def search_keyword(
#         self, keyword: str, page: int = 1, limit: int = 50
#     ) -> Optional[Dict]:
#         """Search for keyword using ProxyClient with automatic rotation."""
#         params = {
#             "q": keyword,
#             "page": page,
#             "limit": limit,
#         }

#         try:
#             # Build full URL with params
#             from urllib.parse import urlencode
#             url = f"{BASE_SEARCH_URL}?{urlencode(params)}"
            
#             print(f"[SEARCH] Querying: {keyword} (page {page})")
            
#             # Use ProxyClient.get() which handles all proxy rotation
#             response = await self.proxy_client.get(
#                 url,
#                 headers=HEADERS,
#                 impersonate="chrome120"
#             )

#             if response.status_code == 200:
#                 return response.json()
#             else:
#                 print(f"[ERROR] HTTP {response.status_code} for '{keyword}' page {page}")
#                 return None

#         except Exception as e:
#             print(f"[ERROR] Search failed for '{keyword}' page {page}: {e}")
#             return None

#     def extract_rankings(
#         self, keyword: str, search_data: Dict, page: int = 1
#     ) -> List[Dict]:
#         """Extract product rankings from search response."""
#         rankings = []
#         hits = search_data.get("hits", [])

#         for idx, product in enumerate(hits, start=1):
#             global_rank = (page - 1) * len(hits) + idx

#             rank_data = {
#                 "timestamp": datetime.now().isoformat(),
#                 "keyword": keyword,
#                 "page": page,
#                 "position_on_page": idx,
#                 "global_rank": global_rank,
#                 "product_id": product.get("id"),
#                 "product_name": product.get("name"),
#                 "product_sku": product.get("sku"),
#                 "brand": product.get("brand_name"),
#                 "price": product.get("price"),
#                 "original_price": product.get("original_price"),
#                 "discount_percent": product.get("discount_percent"),
#                 "rating": product.get("average_rating"),
#                 "review_count": product.get("review_count"),
#                 "in_stock": product.get("in_stock"),
#                 "url": product.get("url"),
#             }

#             rankings.append(rank_data)

#         return rankings

#     async def save_ranking(self, rank_data: Dict) -> None:
#         """Save ranking data to JSONL file."""
#         try:
#             async with aiofiles.open(RESULTS_FILE, "a") as f:
#                 await f.write(json.dumps(rank_data, ensure_ascii=False) + "\n")
#         except Exception as e:
#             print(f"[SAVE ERROR] {e}")

#     def print_rankings_summary(
#         self, keyword: str, rankings: List[Dict], total_hits: int, total_pages: int
#     ) -> None:
#         """Print a summary of search rankings."""
#         print(f"\n{'='*70}")
#         print(f"SEARCH RANKING: {keyword}")
#         print(f"{'='*70}")
#         print(f"Total Hits: {total_hits:,}")
#         print(f"Total Pages: {total_pages}")
#         print(f"Results on Current Page: {len(rankings)}")
#         print(f"{'='*70}")
#         print(f"{'Rank':<6} {'Brand':<20} {'Product':<30} {'Price'}")
#         print(f"{'-'*70}")

#         for rank in rankings[:10]:
#             name = rank["product_name"][:27] if rank["product_name"] else "N/A"
#             brand = rank["brand"][:17] if rank["brand"] else "N/A"
#             price = f"AED {rank['price']}" if rank["price"] else "N/A"

#             print(
#                 f"{rank['global_rank']:<6} "
#                 f"{brand:<20} "
#                 f"{name:<30} "
#                 f"{price}"
#             )

#         print(f"{'='*70}\n")

#     async def search_and_track(
#         self, keyword: str, pages: int = 1, save_results: bool = True
#     ) -> Dict:
#         """
#         Search for keyword and track all rankings.
#         """
#         all_rankings = []
#         total_hits = 0
#         total_pages = 0

#         print(f"\n[SEARCHING] '{keyword}'...")

#         for page in range(1, pages + 1):
#             search_data = await self.search_keyword(keyword, page=page)

#             if not search_data:
#                 print(f"[WARN] Failed to fetch page {page}, skipping...")
#                 continue

#             # Extract data
#             rankings = self.extract_rankings(keyword, search_data, page=page)
#             total_hits = search_data.get("nbHits", 0)
#             total_pages = search_data.get("nbPages", 0)

#             all_rankings.extend(rankings)

#             # Save individual rankings
#             if save_results:
#                 for rank in rankings:
#                     await self.save_ranking(rank)

#             # Print summary for first page
#             if page == 1:
#                 self.print_rankings_summary(keyword, rankings, total_hits, total_pages)

#             print(f"[PAGE {page}] Fetched {len(rankings)} products")

#             # Small delay between pages
#             if page < pages:
#                 await asyncio.sleep(random.uniform(1, 2))

#         return {
#             "keyword": keyword,
#             "total_hits": total_hits,
#             "total_pages": total_pages,
#             "fetched_pages": pages,
#             "total_products_tracked": len(all_rankings),
#             "rankings": all_rankings,
#         }


# async def main():
#     """Main function."""
#     ranker = KeywordSearchRanker()

#     try:
#         # Example: Search for multiple keywords
#         keywords = ["iphone 16 pro", "samsung galaxy s24", "macbook air m3"]

#         for keyword in keywords:
#             result = await ranker.search_and_track(keyword, pages=2, save_results=True)

#             print(f"\n[SUMMARY] {keyword}")
#             print(f"  Total Hits: {result['total_hits']:,}")
#             print(f"  Total Pages: {result['total_pages']}")
#             print(f"  Products Tracked: {result['total_products_tracked']}")

#             # Delay between keywords
#             await asyncio.sleep(random.uniform(2, 3))

#         print(f"\n[COMPLETE] Rankings saved to {RESULTS_FILE}")

#     except Exception as e:
#         print(f"[ERROR] {e}")
#         import traceback
#         traceback.print_exc()

#     finally:
#         # Cleanup
#         await ranker.proxy_client.close_all_sessions()
#         ranker.proxy_manager.shutdown()


# if __name__ == "__main__":
#     try:
#         asyncio.run(main())
#     except KeyboardInterrupt:
#         print("\n[INTERRUPTED]")


import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

import aiofiles


sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)) + "/..")

from proxy.proxy_manager import ProxyManager, ProxyConfig, InMemoryStorage
from proxy.proxy_client import ProxyClient
from proxy.proxies import proxy_urls  # Import your proxy URLs

# ───────────────────────── CONFIG ─────────────────────────

BASE_SEARCH_URL = (
    "https://www.noon.com/_vs/nc/mp-customer-catalog-api"
    "/api/v3/u/search"
)

OUTPUT_DIR = "keyword_rankings"
RESULTS_FILE = os.path.join(OUTPUT_DIR, "rankings.jsonl")

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "referer": "https://www.noon.com/uae-en/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "x-platform": "web",
    "x-mp-country": "ae",
    "x-locale": "en-ae",
    "x-content": "desktop",
    "x-ecom-zonecode": "AE_DXB-S3",
}

# ───────────────────────── PROXY SETUP ─────────────────────────


def build_proxy_manager() -> tuple[ProxyManager, ProxyClient, int]:
    config = ProxyConfig()

    config.timeout = 60.0

    config.proxy_cooldown_on_429 = 20.0
    config.cooldown_on_403 = 30.0
    config.proxy_cooldown_on_timeout = 20.0
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


# ───────────────────────── RANKER ─────────────────────────


class KeywordSearchRanker:

    def __init__(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        self.proxy_manager, self.proxy_client, self.proxy_count = (
            build_proxy_manager()
        )

        self.stats = {
            "requests_ok": 0,
            "requests_failed": 0,
            "start_time": time.time(),
        }

    # ───────────────────────── SEARCH ─────────────────────────

    # async def search_keyword(
    #     self,
    #     keyword: str,
    #     page: int = 1,
    #     limit: int = 50,
    # ) -> Optional[Dict]:

    #     params = {
    #         "q": keyword,
    #         "page": page,
    #         "limit": limit,
    #     }

    #     try:
    #         print(
    #             f"[SEARCH] keyword='{keyword}' "
    #             f"page={page}"
    #         )

    #         response = await self.proxy_client.get(
    #             BASE_SEARCH_URL,
    #             headers=HEADERS,
    #             params=params,

    #             # IMPORTANT FIXES
    #             impersonate="chrome124",

    #             http_version="v1",

    #             curl_options={
    #                 # disable http2 completely
    #                 84: 1,

    #                 # disable multiplexing
    #                 300: 0,

    #                 # fresh connection
    #                 75: 1,

    #                 # forbid reuse
    #                 64: 1,
    #             },
    #         )

    #         print(
    #             f"[HTTP {response.status_code}] "
    #             f"keyword='{keyword}' "
    #             f"page={page}"
    #         )

    #         if response.status_code != 200:
    #             print(response.text[:500])
    #             self.stats["requests_failed"] += 1
    #             return None

    #         self.stats["requests_ok"] += 1
    #         return response.json()

    #     except Exception as e:
    #         print(
    #             f"[PROXY ERROR] "
    #             f"keyword='{keyword}' "
    #             f"page={page} → {e}"
    #         )

    #         self.stats["requests_failed"] += 1
    #         return None

    #     except Exception as e:
    #         print(
    #             f"[ERROR] "
    #             f"keyword='{keyword}' "
    #             f"page={page} → {e}"
    #         )

    #         self.stats["requests_failed"] += 1
    #         return None

    async def search_keyword(
        self,
        keyword: str,
        page: int = 1,
        limit: int = 50,
    ) -> Optional[Dict]:

        params = {
            "q": keyword,
            "page": page,
            "limit": limit,
        }

        try:
            print(
                f"[SEARCH] keyword='{keyword}' "
                f"page={page}"
            )

            response = await self.proxy_client.get(
                BASE_SEARCH_URL,
                headers=HEADERS,
                params=params,
                impersonate="chrome124",
            )

            print(
                f"[HTTP {response.status_code}] "
                f"keyword='{keyword}' "
                f"page={page}"
            )

            if response.status_code != 200:
                print(response.text[:500])
                self.stats["requests_failed"] += 1
                return None

            self.stats["requests_ok"] += 1
            return response.json()

        except Exception as e:
            print(
                f"[ERROR] "
                f"keyword='{keyword}' "
                f"page={page} → {e}"
            )

            self.stats["requests_failed"] += 1
            return None

    # ───────────────────────── EXTRACT ─────────────────────────

    def extract_rankings(
        self,
        keyword: str,
        search_data: Dict,
        page: int = 1,
    ) -> List[Dict]:

        rankings = []

        hits = search_data.get("hits", [])

        for idx, product in enumerate(hits, start=1):

            global_rank = ((page - 1) * len(hits)) + idx

            rank_data = {
                "timestamp": datetime.now().isoformat(),
                "keyword": keyword,
                "page": page,
                "position_on_page": idx,
                "global_rank": global_rank,
                "product_id": product.get("id"),
                "product_name": product.get("name"),
                "product_sku": product.get("sku"),
                "brand": product.get("brand_name"),
                "price": product.get("price"),
                "original_price": product.get("original_price"),
                "discount_percent": product.get("discount_percent"),
                "rating": product.get("average_rating"),
                "review_count": product.get("review_count"),
                "in_stock": product.get("in_stock"),
                "url": product.get("url"),
            }

            rankings.append(rank_data)

        return rankings

    # ───────────────────────── SAVE ─────────────────────────

    async def save_ranking(self, rank_data: Dict) -> None:

        try:
            async with aiofiles.open(
                RESULTS_FILE,
                "a",
                encoding="utf-8",
            ) as f:
                await f.write(
                    json.dumps(
                        rank_data,
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        except Exception as e:
            print(f"[SAVE ERROR] {e}")

    # ───────────────────────── SUMMARY ─────────────────────────

    def print_rankings_summary(
        self,
        keyword: str,
        rankings: List[Dict],
        total_hits: int,
        total_pages: int,
    ) -> None:

        print(f"\n{'=' * 80}")
        print(f"SEARCH RANKING: {keyword}")
        print(f"{'=' * 80}")

        print(f"Total Hits: {total_hits:,}")
        print(f"Total Pages: {total_pages}")
        print(f"Results On Page: {len(rankings)}")

        print(f"{'-' * 80}")
        print(
            f"{'Rank':<6} "
            f"{'Brand':<20} "
            f"{'Product':<35} "
            f"{'Price'}"
        )
        print(f"{'-' * 80}")

        for rank in rankings[:10]:

            name = (
                rank["product_name"][:32]
                if rank["product_name"]
                else "N/A"
            )

            brand = (
                rank["brand"][:17]
                if rank["brand"]
                else "N/A"
            )

            price = (
                f"AED {rank['price']}"
                if rank["price"]
                else "N/A"
            )

            print(
                f"{rank['global_rank']:<6} "
                f"{brand:<20} "
                f"{name:<35} "
                f"{price}"
            )

        print(f"{'=' * 80}\n")

    # ───────────────────────── TRACK ─────────────────────────

    async def search_and_track(
        self,
        keyword: str,
        pages: int = 1,
        save_results: bool = True,
    ) -> Dict:

        all_rankings = []

        total_hits = 0
        total_pages = 0

        print(f"\n[TRACKING] '{keyword}'")

        for page in range(1, pages + 1):

            search_data = await self.search_keyword(
                keyword=keyword,
                page=page,
            )

            if not search_data:
                print(
                    f"[WARN] "
                    f"Failed page {page} "
                    f"for '{keyword}'"
                )
                continue

            rankings = self.extract_rankings(
                keyword=keyword,
                search_data=search_data,
                page=page,
            )

            total_hits = search_data.get("nbHits", 0)
            total_pages = search_data.get("nbPages", 0)

            all_rankings.extend(rankings)

            if save_results:
                for rank in rankings:
                    await self.save_ranking(rank)

            if page == 1:
                self.print_rankings_summary(
                    keyword,
                    rankings,
                    total_hits,
                    total_pages,
                )

            print(
                f"[PAGE {page}] "
                f"products={len(rankings)}"
            )

            await asyncio.sleep(random.uniform(1.0, 2.5))

        return {
            "keyword": keyword,
            "total_hits": total_hits,
            "total_pages": total_pages,
            "products_tracked": len(all_rankings),
            "rankings": all_rankings,
        }

    # ───────────────────────── CLOSE ─────────────────────────

    async def close(self):

        await self.proxy_client.close_all_sessions()

        elapsed = time.time() - self.stats["start_time"]

        print("\n══════════════════════════════")
        print("KEYWORD TRACKING COMPLETE")
        print(f"requests_ok={self.stats['requests_ok']}")
        print(f"requests_failed={self.stats['requests_failed']}")
        print(f"elapsed={elapsed:.1f}s")
        print("══════════════════════════════")


async def main():

    ranker = KeywordSearchRanker()

    try:
        keywords = [
            "iphone",
            "samsung",
            "macbook",
        ]

        for keyword in keywords:

            result = await ranker.search_and_track(
                keyword=keyword,
                pages=1,
                save_results=True,
            )

            print(f"\n[SUMMARY] {keyword}")
            print(f"  Total Hits: {result['total_hits']:,}")
            print(f"  Total Pages: {result['total_pages']}")
            print(
                f"  Products Tracked: "
                f"{result['products_tracked']}"
            )

            await asyncio.sleep(random.uniform(2, 4))

        print(
            f"\n[DONE] "
            f"Saved rankings to {RESULTS_FILE}"
        )

    except Exception as e:
        print(f"[FATAL ERROR] {e}")

        import traceback
        traceback.print_exc()

    finally:
        await ranker.close()


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")