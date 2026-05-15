#THIS will scrap the product catalog of noon.com starting from a given category, and save results in batches of 10k products.
#This will be running concurrently with multiple tasks to speed up the process, while respecting a delay between requests to avoid overwhelming the server.
#
# PROXY INTEGRATION:
#   Uses the ProxyClient/ProxyManager system for automatic proxy rotation,
#   retry logic with exponential backoff, cooldown management, and DNS caching.
#   Proxies are loaded from proxy/proxies.py (BrightData static IPs).
#
# SCALE OPTIMIZATIONS:
#   - Concurrency scales with proxy pool size (not a fixed semaphore)
#   - Per-proxy rate limiting via ProxyManager cooldowns
#   - Automatic retry with different proxy on 429/403/5xx/timeout
#   - Progressive backoff on repeated proxy failures
#   - Failed categories are re-queued with a retry limit
#   - Periodic proxy health logging
#   - Adaptive worker pool based on available proxies

import asyncio
import aiofiles
import json
import os
import sys
import time
import random
from typing import Optional

# Ensure project root is on sys.path for proxy imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from proxy.proxy_client import ProxyClient, ProxyHTTPError
from proxy.proxy_manager import ProxyManager, ProxyConfig, InMemoryStorage
from proxy.proxies import proxy_urls

# ─────────────────────────── CONFIGURATION ───────────────────────────────────

BASE_URL = "https://www.noon.com/_vs/nc/mp-customer-catalog-api/api/v3/u/"
START_CAT = "hajj-health-essentials"
OUTPUT_DIR = "output"
STATE_FILE = "state.json"
BATCH_SIZE = 10000
PAGE_LIMIT = 50

# ── Concurrency & Rate Limiting ──
# Max concurrent category workers (will be capped by proxy pool size)
MAX_WORKERS = 30
# Max concurrent page fetches within a single category
MAX_PAGES_CONCURRENT = 10
# Delay between spawning new category workers (seconds)
WORKER_SPAWN_DELAY = 0.1
# Base delay between page fetches within a category (seconds)
PAGE_FETCH_DELAY = 0.2
# How many times to retry a failed category before giving up
MAX_CATEGORY_RETRIES = 3
# Interval for logging proxy pool health (seconds)
HEALTH_LOG_INTERVAL = 30

# ── Cookie & Headers ──
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
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "x-border-enabled": "true",
    "x-cms": "v2",
    "x-content": "desktop",
    "x-ecom-zonecode": "AE_DXB-S14",
    "Cookie": COOKIE,
}


# ─────────────────────────── PROXY SETUP ─────────────────────────────────────

def build_proxy_manager() -> tuple[ProxyManager, int]:
    """
    Build a local ProxyManager loaded with proxies from proxy/proxies.py.

    Returns (manager, proxy_count).
    Uses InMemoryStorage since this is a single-process scraper.
    Configures timeouts and cooldowns tuned for noon.com scraping at scale.
    """
    config = ProxyConfig()
    # Tune for scraping: shorter timeouts, moderate cooldowns
    config.timeout = 30.0
    config.proxy_cooldown_on_429 = 15.0      # noon rate-limit: cool off 15s
    config.cooldown_on_403 = 20.0             # forbidden: cool off 20s
    config.proxy_cooldown_on_timeout = 10.0   # timeout: brief cooldown
    config.cooldown_on_5xx = 8.0              # server error: brief cooldown
    config.default_cooldown = 10.0
    config.proxy_cooldown_on_connection_error = 15.0
    config.max_attempts_per_request = 4       # retry up to 4 times per request
    config.progressive_failure_threshold = 3  # exponential backoff after 3 failures
    config.reservation_ttl = 60.0             # 60s reservation window
    config.browser_impersonation = "chrome120"

    storage = InMemoryStorage()
    manager = ProxyManager(config=config, storage_backend=storage, platform="noon")

    # Collect all proxy URLs from proxy/proxies.py
    all_proxy_urls = []
    for key, urls in proxy_urls.items():
        if isinstance(urls, list):
            all_proxy_urls.extend(urls)

    loaded = manager.load_proxies_from_url_list(all_proxy_urls)
    print(f"[PROXY] Loaded {loaded} proxies from {len(proxy_urls)} groups")

    return manager, loaded


# ─────────────────────────── SCRAPER CLASS ────────────────────────────────────

class NoonScraper:
    def __init__(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        self.state = self.load_state()
        self.visited = set(self.state["visited"])
        self.total = [self.state["total"]]
        self.batch_index = self.state["batch_index"]
        self.batch_buffer = []
        self.file_sem = asyncio.Semaphore(1)
        self.queue = asyncio.Queue()

        # Track retries per category
        self._retry_counts: dict[str, int] = {}

        # Proxy infrastructure
        self.proxy_manager, self.proxy_count = build_proxy_manager()
        self.proxy_client = ProxyClient(
            config=self.proxy_manager.config,
            proxy_manager=self.proxy_manager,
        )

        # Scale concurrency based on proxy pool:
        # Use min(MAX_WORKERS, proxy_count // 3) to avoid exhausting all proxies
        # (each category may fire multiple page requests concurrently)
        effective_workers = min(MAX_WORKERS, max(5, self.proxy_count // 3))
        self.worker_sem = asyncio.Semaphore(effective_workers)
        print(f"[CONFIG] Workers={effective_workers}  Proxies={self.proxy_count}  "
              f"MaxPagesConc={MAX_PAGES_CONCURRENT}  MaxRetries={MAX_CATEGORY_RETRIES}")

        # Stats
        self._stats = {
            "categories_done": 0,
            "categories_failed": 0,
            "categories_skipped": 0,
            "pages_fetched": 0,
            "pages_failed": 0,
            "start_time": time.time(),
        }

    def cat_filename(self, cat):
        safe = cat.replace("/", "_")
        return os.path.join(OUTPUT_DIR, f"cat_{safe}.jsonl")

    def load_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
        return {"visited": [], "queue": [START_CAT], "total": 0, "batch_index": 1}

    async def save_state(self, queue_snapshot):
        async with aiofiles.open(STATE_FILE, "w") as f:
            await f.write(json.dumps({
                "visited": list(self.visited),
                "queue": queue_snapshot,
                "total": self.total[0],
                "batch_index": self.batch_index,
            }))

    def get_child_categories(self, data):
        codes = []
        for facet in data.get("facets", []):
            if facet.get("code") == "category":
                for root in facet.get("data", []):
                    self._walk(root, codes)
        return codes

    def _walk(self, node, out):
        if code := node.get("code"):
            out.append(code)
        for child in node.get("children", []):
            self._walk(child, out)

    # ── Fetch with ProxyClient ───────────────────────────────────────────────

    async def fetch_page(self, cat: str, page: int) -> Optional[dict]:
        """
        Fetch a single category page via ProxyClient.

        The ProxyClient handles:
        - Automatic proxy selection and rotation
        - Retry with different proxy on failure (up to max_attempts_per_request)
        - Cooldown management for rate-limited/blocked proxies
        - DNS caching to avoid resolution bottlenecks
        - Browser impersonation via curl_cffi
        """
        url = BASE_URL + cat
        try:
            response = await self.proxy_client.get(
                url,
                headers=HEADERS,
                params={"page": page, "limit": PAGE_LIMIT},
            )
            if response.status_code == 200:
                self._stats["pages_fetched"] += 1
                return response.json()
            else:
                print(f"[HTTP {response.status_code}] {cat} page={page}")
                self._stats["pages_failed"] += 1
                return None

        except ProxyHTTPError as e:
            print(f"[PROXY ERROR] {cat} page={page} → {e}")
            self._stats["pages_failed"] += 1
            return None

        except Exception as e:
            print(f"[ERROR] {cat} page={page} → {type(e).__name__}: {e}")
            self._stats["pages_failed"] += 1
            return None

    # ── Batch output ─────────────────────────────────────────────────────────

    async def flush_batch(self, force=False):
        async with self.file_sem:
            while len(self.batch_buffer) >= BATCH_SIZE or (force and self.batch_buffer):
                chunk = self.batch_buffer[:BATCH_SIZE]
                self.batch_buffer = self.batch_buffer[BATCH_SIZE:]
                filename = os.path.join(OUTPUT_DIR, f"products_batch_{self.batch_index}.jsonl")
                async with aiofiles.open(filename, "a", encoding="utf-8") as f:
                    await f.write("\n".join(json.dumps(p, ensure_ascii=False) for p in chunk) + "\n")
                print(f"[BATCH] Wrote {len(chunk)} products → {filename}")
                self.batch_index += 1

    async def save_category_file(self, cat, hits):
        async with aiofiles.open(self.cat_filename(cat), "w", encoding="utf-8") as f:
            await f.write("\n".join(json.dumps(h, ensure_ascii=False) for h in hits) + "\n")

    # ── Category processing ──────────────────────────────────────────────────

    async def process_category(self, cat: str) -> bool:
        """
        Process a single category: fetch all pages, discover children, save results.

        Returns True on success, False on failure (will be re-queued).
        """
        if os.path.exists(self.cat_filename(cat)):
            print(f"[SKIP] {cat} already fetched")
            self._stats["categories_skipped"] += 1
            return True

        # ── Page 1: discover children + get first page of results ─────────
        data = await self.fetch_page(cat, 1)
        if data is None:
            return False  # signal for retry

        # Discover and enqueue child categories
        for code in self.get_child_categories(data):
            if code not in self.visited:
                self.visited.add(code)
                await self.queue.put(code)

        nb_pages = data.get("nbPages", 1)
        all_hits = data.get("hits", [])

        # ── Remaining pages: fetch concurrently with bounded parallelism ──
        if nb_pages > 1:
            page_sem = asyncio.Semaphore(MAX_PAGES_CONCURRENT)

            async def fetch_with_limit(p):
                async with page_sem:
                    # Small stagger to avoid burst
                    await asyncio.sleep(PAGE_FETCH_DELAY * random.uniform(0.5, 1.5))
                    return await self.fetch_page(cat, p)

            page_tasks = [fetch_with_limit(p) for p in range(2, nb_pages + 1)]
            results = await asyncio.gather(*page_tasks)

            for result in results:
                if result:
                    all_hits.extend(result.get("hits", []))

        # Tag all hits with category
        for h in all_hits:
            h["_category"] = cat
        self.total[0] += len(all_hits)

        elapsed = time.time() - self._stats["start_time"]
        rate = self.total[0] / elapsed if elapsed > 0 else 0
        print(f"[DONE] {cat:45s} hits={len(all_hits):5d}  "
              f"total={self.total[0]:7d}  rate={rate:.0f}/s  "
              f"pages={nb_pages}")

        # Save category file
        await self.save_category_file(cat, all_hits)

        # Buffer for batch output
        async with self.file_sem:
            self.batch_buffer.extend(all_hits)

        await self.flush_batch()
        self._stats["categories_done"] += 1
        return True

    # ── Worker loop ──────────────────────────────────────────────────────────

    async def worker(self, worker_id: int):
        """
        Worker coroutine that pulls categories from the queue and processes them.
        Uses a semaphore to limit overall concurrency.
        Failed categories are re-queued with retry tracking.
        """
        while True:
            try:
                cat = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            async with self.worker_sem:
                success = await self.process_category(cat)

                if not success:
                    # Track retries
                    retries = self._retry_counts.get(cat, 0)
                    if retries < MAX_CATEGORY_RETRIES:
                        self._retry_counts[cat] = retries + 1
                        # Re-queue with exponential backoff delay
                        backoff = min(2 ** retries, 10) + random.uniform(0, 2)
                        print(f"[RETRY] {cat} → attempt {retries + 1}/{MAX_CATEGORY_RETRIES} "
                              f"(backoff {backoff:.1f}s)")
                        await asyncio.sleep(backoff)
                        await self.queue.put(cat)
                    else:
                        print(f"[FAILED] {cat} → gave up after {MAX_CATEGORY_RETRIES} retries")
                        self._stats["categories_failed"] += 1

            self.queue.task_done()

    # ── Health monitor ───────────────────────────────────────────────────────

    async def health_monitor(self):
        """Periodically log proxy pool health and scraper stats."""
        while True:
            await asyncio.sleep(HEALTH_LOG_INTERVAL)
            try:
                status = self.proxy_manager.get_status()
                elapsed = time.time() - self._stats["start_time"]
                rate = self.total[0] / elapsed if elapsed > 0 else 0

                print(
                    f"\n{'─' * 80}\n"
                    f"[HEALTH] Elapsed={elapsed:.0f}s  Products={self.total[0]}  Rate={rate:.0f}/s\n"
                    f"[HEALTH] Categories: done={self._stats['categories_done']}  "
                    f"failed={self._stats['categories_failed']}  "
                    f"skipped={self._stats['categories_skipped']}  "
                    f"queued={self.queue.qsize()}\n"
                    f"[HEALTH] Pages: fetched={self._stats['pages_fetched']}  "
                    f"failed={self._stats['pages_failed']}\n"
                    f"[HEALTH] Proxies: total={status['total_proxies']}  "
                    f"available={status['available_proxies']}  "
                    f"reserved={status['active_reservations']}  "
                    f"cooldown={status['active_cooldowns']}\n"
                    f"{'─' * 80}"
                )
            except Exception as e:
                print(f"[HEALTH ERROR] {e}")

    # ── Main run loop ────────────────────────────────────────────────────────

    async def run(self):
        # Seed the queue from saved state
        for cat in self.state["queue"]:
            if cat not in self.visited:
                self.visited.add(cat)
                await self.queue.put(cat)

        if self.queue.empty():
            self.visited.add(START_CAT)
            await self.queue.put(START_CAT)

        print(f"\n{'═' * 80}")
        print(f"  NOON CATALOG SCRAPER — Proxy-Powered Concurrent Edition")
        print(f"  Queue={self.queue.qsize()}  Visited={len(self.visited)}  "
              f"Saved={self.total[0]}  Proxies={self.proxy_count}")
        print(f"{'═' * 80}\n")

        # Start health monitor
        health_task = asyncio.create_task(self.health_monitor())

        try:
            # Main processing loop:
            # We keep spawning worker batches as long as the queue has items.
            # Workers may add new categories to the queue (child discovery),
            # so we loop until the queue is truly empty and all workers are done.
            while True:
                if self.queue.empty():
                    break

                # Spawn a batch of workers for current queue contents
                workers = []
                batch_size = min(self.queue.qsize(), MAX_WORKERS)
                for i in range(batch_size):
                    workers.append(asyncio.create_task(self.worker(i)))
                    # Small stagger to avoid thundering herd
                    await asyncio.sleep(WORKER_SPAWN_DELAY)

                # Wait for all workers in this batch to finish
                if workers:
                    await asyncio.gather(*workers, return_exceptions=True)

                # Save state after each batch
                await self.save_state([])

                # Brief pause before checking for newly discovered categories
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            print("\n[CANCELLED] Saving state...")

        except KeyboardInterrupt:
            print("\n[INTERRUPTED] Saving state...")

        finally:
            health_task.cancel()
            try:
                await health_task
            except asyncio.CancelledError:
                pass

        # Final flush and state save
        await self.flush_batch(force=True)
        await self.save_state([])

        # Close proxy client sessions
        await self.proxy_client.close_all_sessions()

        # Final stats
        elapsed = time.time() - self._stats["start_time"]
        rate = self.total[0] / elapsed if elapsed > 0 else 0

        print(f"\n{'═' * 80}")
        print(f"  SCRAPE COMPLETE")
        print(f"  Total products : {self.total[0]}")
        print(f"  Categories done: {self._stats['categories_done']}")
        print(f"  Categories fail: {self._stats['categories_failed']}")
        print(f"  Pages fetched  : {self._stats['pages_fetched']}")
        print(f"  Pages failed   : {self._stats['pages_failed']}")
        print(f"  Elapsed time   : {elapsed:.0f}s")
        print(f"  Avg rate       : {rate:.0f} products/s")
        print(f"  Proxies used   : {self.proxy_count}")
        print(f"{'═' * 80}\n")


if __name__ == "__main__":
    try:
        asyncio.run(NoonScraper().run())
    except KeyboardInterrupt:
        print("Interrupted.")