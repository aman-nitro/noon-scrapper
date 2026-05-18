import asyncio
import aiofiles
import json
import os
import sys
import time
import random
from typing import Optional
import psutil
import tracemalloc

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from proxy.proxy_client import ProxyClient, ProxyHTTPError
from proxy.proxy_manager import ProxyManager, ProxyConfig, InMemoryStorage
from proxy.proxies import proxy_urls

# ───────────────────────── CONFIG ─────────────────────────

BASE_URL = "https://www.noon.com/_vs/nc/mp-customer-catalog-api/api/v3/u/"
START_CAT = "hajj-health-essentials"

OUTPUT_DIR = "output"
STATE_FILE = "state.json"

BATCH_SIZE = 10000
PAGE_LIMIT = 50

MAX_WORKERS = 20
MAX_PAGES_CONCURRENT = 5

WORKER_SPAWN_DELAY = 0.1
PAGE_FETCH_DELAY = 0.2

MAX_CATEGORY_RETRIES = 3
HEALTH_LOG_INTERVAL = 30

# COOKIE = "YOUR_COOKIE"

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
    "x-ecom-zonecode": "AE_DXB-S14",
    # "Cookie": COOKIE,
}


# ───────────────────────── PROXY SETUP ─────────────────────────


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

    # IMPORTANT:
    # your 407 issue likely comes from bad auth or dead proxies.
    # cooldown them aggressively.
    config.cooldown_on_407 = 120.0

    storage = InMemoryStorage()

    manager = ProxyManager(
        config=config,
        storage_backend=storage,
        platform="noon"
    )

    all_proxy_urls = []

    for _, urls in proxy_urls.items():
        if isinstance(urls, list):
            all_proxy_urls.extend(urls)

    loaded = manager.load_proxies_from_url_list(all_proxy_urls)

    print(f"[PROXY] Loaded {loaded} proxies")

    return manager, loaded


# ───────────────────────── SCRAPER ─────────────────────────


class NoonScraper:

    def __init__(self):

        os.makedirs(OUTPUT_DIR, exist_ok=True)

        self.state = self.load_state()

        self.visited = set(self.state["visited"])

        self.total = self.state["total"]

        self.batch_index = self.state["batch_index"]

        self.batch_buffer = []

        self.queue = asyncio.Queue()

        self.file_sem = asyncio.Semaphore(1)

        self.retry_counts = {}

        self.stats = {
            "categories_done": 0,
            "categories_failed": 0,
            "pages_fetched": 0,
            "pages_failed": 0,
            "start_time": time.time(),
        }

        # Memory tracking
        self.process = psutil.Process(os.getpid())
        self.memory_stats = {
            "peak_rss_mb": 0,  # Peak RSS (resident set size)
            "peak_vms_mb": 0,  # Peak virtual memory size
            "current_rss_mb": 0,
            "current_vms_mb": 0,
        }
        tracemalloc.start()  # Start Python memory tracking

        self.proxy_manager, self.proxy_count = build_proxy_manager()

        self.proxy_client = ProxyClient(
            config=self.proxy_manager.config,
            proxy_manager=self.proxy_manager,
        )

        self.worker_count = min(
            MAX_WORKERS,
            max(5, self.proxy_count // 5)
        )

        print(
            f"[CONFIG] workers={self.worker_count} proxies={self.proxy_count}"
        )

    # ───────────────────────── STATE ─────────────────────────

    def load_state(self):

        if not os.path.exists(STATE_FILE):
            return {
                "visited": [],
                "queue": [START_CAT],
                "total": 0,
                "batch_index": 1,
            }

        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)

            # old format migration
            if "done" in data or "queued" in data:
                return {
                    "visited": data.get("done", []),
                    "queue": data.get("queued", []),
                    "total": data.get("total", 0),
                    "batch_index": data.get("batch_index", 1),
                }

            return {
                "visited": data.get("visited", []),
                "queue": data.get("queue", [START_CAT]),
                "total": data.get("total", 0),
                "batch_index": data.get("batch_index", 1),
            }

        except Exception as e:
            print(f"[STATE ERROR] {e}")

            return {
                "visited": [],
                "queue": [START_CAT],
                "total": 0,
                "batch_index": 1,
            }

    async def save_state(self):

        queued = list(self.queue._queue)

        async with aiofiles.open(STATE_FILE, "w") as f:
            await f.write(json.dumps({
                "visited": list(self.visited),
                "queue": queued,
                "total": self.total,
                "batch_index": self.batch_index,
            }))

    # ───────────────────────── HELPERS ─────────────────────────

    def cat_filename(self, cat):
        safe = cat.replace("/", "_")
        return os.path.join(OUTPUT_DIR, f"{safe}.jsonl")

    def get_child_categories(self, data):

        codes = []

        for facet in data.get("facets", []):

            if facet.get("code") == "category":

                for root in facet.get("data", []):
                    self.walk(root, codes)

        return codes

    def walk(self, node, out):

        if code := node.get("code"):
            out.append(code)

        for child in node.get("children", []):
            self.walk(child, out)

    # ───────────────────────── FETCH ─────────────────────────

    async def fetch_page(self, cat, page):

        url = BASE_URL + cat

        try:

            response = await self.proxy_client.get(
                url,
                headers=HEADERS,
                params={
                    "page": page,
                    "limit": PAGE_LIMIT,
                }
            )
            print(f"[HTTP {response.status_code}] {cat} page={page}")

            if response.status_code == 200:

                self.stats["pages_fetched"] += 1

                return response.json()


            self.stats["pages_failed"] += 1

            return None

        except ProxyHTTPError as e:

            msg = str(e)

            # specifically detect 407 proxy failures
            if "407" in msg:
                print(f"[PROXY AUTH ERROR] {cat} page={page}")

            else:
                print(f"[PROXY ERROR] {cat} page={page} → {e}")

            self.stats["pages_failed"] += 1

            return None

        except Exception as e:

            print(f"[ERROR] {cat} page={page} → {e}")

            self.stats["pages_failed"] += 1

            return None

    # ───────────────────────── BATCH WRITER ─────────────────────────

    async def flush_batch(self, force=False):

        async with self.file_sem:

            while len(self.batch_buffer) >= BATCH_SIZE or (
                force and self.batch_buffer
            ):

                chunk = self.batch_buffer[:BATCH_SIZE]

                self.batch_buffer = self.batch_buffer[BATCH_SIZE:]

                filename = os.path.join(
                    OUTPUT_DIR,
                    f"products_batch_{self.batch_index}.jsonl"
                )

                async with aiofiles.open(filename, "a") as f:

                    await f.write(
                        "\n".join(
                            json.dumps(x, ensure_ascii=False)
                            for x in chunk
                        ) + "\n"
                    )

                print(f"[BATCH] wrote {len(chunk)} → {filename}")

                self.batch_index += 1

    # ───────────────────────── CATEGORY ─────────────────────────

    async def process_category(self, cat):

        if os.path.exists(self.cat_filename(cat)):
            return True

        first = await self.fetch_page(cat, 1)

        if not first:
            return False

        for code in self.get_child_categories(first):

            if code not in self.visited:

                self.visited.add(code)

                await self.queue.put(code)

        all_hits = first.get("hits", [])

        nb_pages = first.get("nbPages", 1)

        sem = asyncio.Semaphore(MAX_PAGES_CONCURRENT)

        async def fetch_more(page):

            async with sem:

                await asyncio.sleep(
                    PAGE_FETCH_DELAY * random.uniform(0.5, 1.5)
                )

                return await self.fetch_page(cat, page)

        tasks = [
            fetch_more(p)
            for p in range(2, nb_pages + 1)
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True
        )

        for r in results:

            if isinstance(r, dict):
                all_hits.extend(r.get("hits", []))

        for hit in all_hits:
            hit["_category"] = cat

        self.total += len(all_hits)

        async with self.file_sem:
            self.batch_buffer.extend(all_hits)

        await self.flush_batch()

        async with aiofiles.open(
            self.cat_filename(cat),
            "w"
        ) as f:

            await f.write(
                "\n".join(
                    json.dumps(x, ensure_ascii=False)
                    for x in all_hits
                )
            )

        self.stats["categories_done"] += 1

        print(
            f"[DONE] {cat} "
            f"hits={len(all_hits)} "
            f"total={self.total}"
        )

        return True

    # ───────────────────────── WORKER ─────────────────────────

    async def worker(self, wid):

        while True:

            try:
                cat = self.queue.get_nowait()

            except asyncio.QueueEmpty:
                return

            try:

                success = await self.process_category(cat)

                if not success:

                    retries = self.retry_counts.get(cat, 0)

                    if retries < MAX_CATEGORY_RETRIES:

                        self.retry_counts[cat] = retries + 1

                        backoff = min(2 ** retries, 10)

                        print(
                            f"[RETRY] {cat} "
                            f"{retries+1}/{MAX_CATEGORY_RETRIES}"
                        )

                        await asyncio.sleep(backoff)

                        await self.queue.put(cat)

                    else:

                        print(f"[FAILED] {cat}")

                        self.stats["categories_failed"] += 1

            finally:

                self.queue.task_done()

    # ───────────────────────── HEALTH ─────────────────────────

    def update_memory_stats(self):
        """Update current memory statistics and track peak values."""
        try:
            mem_info = self.process.memory_info()
            current_rss_mb = mem_info.rss / (1024 * 1024)
            current_vms_mb = mem_info.vms / (1024 * 1024)

            self.memory_stats["current_rss_mb"] = current_rss_mb
            self.memory_stats["current_vms_mb"] = current_vms_mb

            # Track peak values
            if current_rss_mb > self.memory_stats["peak_rss_mb"]:
                self.memory_stats["peak_rss_mb"] = current_rss_mb
            if current_vms_mb > self.memory_stats["peak_vms_mb"]:
                self.memory_stats["peak_vms_mb"] = current_vms_mb
        except Exception as e:
            print(f"[MEMORY ERROR] {e}")

    async def health_monitor(self):

        while True:

            await asyncio.sleep(HEALTH_LOG_INTERVAL)

            self.update_memory_stats()

            elapsed = time.time() - self.stats["start_time"]

            rate = (
                self.total / elapsed
                if elapsed > 0 else 0
            )

            print(
                f"\n[HEALTH] "
                f"products={self.total} "
                f"rate={rate:.0f}/s "
                f"queue={self.queue.qsize()} "
                f"done={self.stats['categories_done']} "
                f"failed={self.stats['categories_failed']} "
                f"pages_ok={self.stats['pages_fetched']} "
                f"pages_fail={self.stats['pages_failed']} "
                f"RAM={self.memory_stats['current_rss_mb']:.1f}MB "
                f"(peak: {self.memory_stats['peak_rss_mb']:.1f}MB)"
            )

    # ───────────────────────── RUN ─────────────────────────

    async def run(self):

        for cat in self.state["queue"]:

            if cat not in self.visited:

                self.visited.add(cat)

                await self.queue.put(cat)

        if self.queue.empty():

            self.visited.add(START_CAT)

            await self.queue.put(START_CAT)

        print(
            f"\n[START] queue={self.queue.qsize()} "
            f"visited={len(self.visited)} "
            f"saved={self.total}"
        )

        health_task = asyncio.create_task(
            self.health_monitor()
        )

        try:

            while not self.queue.empty():

                workers = []

                for i in range(self.worker_count):

                    workers.append(
                        asyncio.create_task(
                            self.worker(i)
                        )
                    )

                    await asyncio.sleep(
                        WORKER_SPAWN_DELAY
                    )

                await asyncio.gather(
                    *workers,
                    return_exceptions=True
                )

                await self.save_state()

        except KeyboardInterrupt:

            print("\n[INTERRUPTED]")

        finally:

            health_task.cancel()

            await self.flush_batch(force=True)

            await self.save_state()

            await self.proxy_client.close_all_sessions()

            # Final memory update
            self.update_memory_stats()
            current_memory_mb, peak_memory_mb = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            elapsed = (
                time.time()
                - self.stats["start_time"]
            )

            rate = (
                self.total / elapsed
                if elapsed > 0 else 0
            )

            print("\n══════════════════════════════")
            print("SCRAPE COMPLETE")
            print(f"products={self.total}")
            print(f"done={self.stats['categories_done']}")
            print(f"failed={self.stats['categories_failed']}")
            print(f"pages_ok={self.stats['pages_fetched']}")
            print(f"pages_fail={self.stats['pages_failed']}")
            print(f"rate={rate:.0f}/s")
            print("\n──── MEMORY METRICS ────")
            print(f"Peak RSS Memory: {self.memory_stats['peak_rss_mb']:.1f} MB")
            print(f"Current RSS Memory: {self.memory_stats['current_rss_mb']:.1f} MB")
            print(f"Peak Virtual Memory: {self.memory_stats['peak_vms_mb']:.1f} MB")
            print(f"Python Tracemalloc Peak: {peak_memory_mb / (1024*1024):.1f} MB")
            print("══════════════════════════════")


if __name__ == "__main__":

    try:
        asyncio.run(NoonScraper().run())

    except KeyboardInterrupt:

        print("Interrupted")