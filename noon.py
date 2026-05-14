import asyncio
import aiohttp
import aiofiles
import json
import os

BASE_URL = "https://www.noon.com/_vs/nc/mp-customer-catalog-api/api/v3/u/"
START_CAT = "hajj-health-essentials"
OUTPUT_DIR = "output"
STATE_FILE = "state.json"
BATCH_SIZE = 10000
CONCURRENCY = 10
PAGE_LIMIT = 50
DELAY = 0.4

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
    # "x-ab-test": "1331,1941,2161,2631,3022,2900,3431,1651,2541,2840,3611,1891,2341,3592,2891,3315,3581,1931,2561,3491,1162,1750,1960,2042,2201,1531,3321,3530,3721,671,881,3450,3711,1832,2771,3701,3651,2424,2881,3662,3150,3621,3071,3571,3390,2001,2222,2690,2941,3792,2781,3001,2211,2531,2681,3442,3470,1881,2451,3031,3272,1581,1771,1802,2910,2071,2751,3183,3281,3142,1471,2351,2962,3630,3561,3050,1250,3350,3361,3503,1451,3162",
    "x-border-enabled": "true",
    "x-cms": "v2",
    "x-content": "desktop",
    "x-ecom-zonecode": "AE_DXB-S14",
    # "x-lat": "252116403",
    # "x-lng": "552706049",
    # "x-locale": "en-ae",
    # "x-mp-country": "ae",
    # "x-platform": "web",
    # "x-rocket-enabled": "true",
    # "x-rocket-zonecode": "W00068765A",
    # "x-visitor-id": "d7adf681-747a-4c96-bfbb-b19ed13f4280",
    "Cookie": COOKIE,
}


class NoonScraper:
    def __init__(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        self.state = self.load_state()
        self.visited = set(self.state["visited"])
        self.total = [self.state["total"]]
        self.batch_index = self.state["batch_index"]
        self.batch_buffer = []
        self.sem = asyncio.Semaphore(CONCURRENCY)
        self.file_sem = asyncio.Semaphore(1)
        self.queue = asyncio.Queue()

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

    async def fetch_page(self, session, cat, page):
        async with self.sem:
            try:
                async with session.get(
                    BASE_URL + cat,
                    params={"page": page, "limit": PAGE_LIMIT},
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as r:
                    if r.status == 200:
                        return await r.json(content_type=None)
                    print(f"[HTTP {r.status}] {cat} page={page}")
            except Exception as e:
                print(f"[ERROR] {cat} page={page} → {type(e).__name__}: {e}")
            return None

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

    async def process_category(self, session, cat):
        if os.path.exists(self.cat_filename(cat)):
            print(f"[SKIP] {cat} already fetched")
            return

        data = await self.fetch_page(session, cat, 1)
        if data is None:
            return

        for code in self.get_child_categories(data):
            if code not in self.visited:
                self.visited.add(code)
                await self.queue.put(code)

        nb_pages = data.get("nbPages", 1)
        all_hits = data.get("hits", [])

        page_tasks = [self.fetch_page(session, cat, p) for p in range(2, nb_pages + 1)]
        for result in await asyncio.gather(*page_tasks):
            if result:
                all_hits.extend(result.get("hits", []))

        for h in all_hits:
            h["_category"] = cat
        self.total[0] += len(all_hits)

        print(f"[DONE] {cat:45s} hits={len(all_hits)}  total={self.total[0]}")

        await self.save_category_file(cat, all_hits)

        async with self.file_sem:
            self.batch_buffer.extend(all_hits)

        await self.flush_batch()
        await asyncio.sleep(DELAY)

    async def run(self):
        for cat in self.state["queue"]:
            if cat not in self.visited:
                self.visited.add(cat)
                await self.queue.put(cat)

        if self.queue.empty():
            self.visited.add(START_CAT)
            await self.queue.put(START_CAT)

        print(f"Starting — queue={self.queue.qsize()}  visited={len(self.visited)}  saved={self.total[0]}")

        connector = aiohttp.TCPConnector(limit=CONCURRENCY + 5)
        async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
            active: set[asyncio.Task] = set()

            try:
                while True:
                    while not self.queue.empty():
                        cat = await self.queue.get()
                        task = asyncio.create_task(self.process_category(session, cat))
                        active.add(task)
                        task.add_done_callback(active.discard)

                    if not active:
                        break

                    await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
                    await self.save_state([])

            except asyncio.CancelledError:
                for t in active:
                    t.cancel()
                await asyncio.gather(*active, return_exceptions=True)

        await self.flush_batch(force=True)
        await self.save_state([])
        print(f"\nDone. Total products: {self.total[0]}  Categories: {len(self.visited)}")


if __name__ == "__main__":
    try:
        asyncio.run(NoonScraper().run())
    except KeyboardInterrupt:
        print("Interrupted.")