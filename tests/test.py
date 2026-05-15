import asyncio
import json
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import ProxyClient and dependencies
from proxy.proxy_client import ProxyClient, ProxyHTTPError

BASE_URL = "https://www.noon.com/_vs/nc/mp-customer-catalog-api/api/v3/u/"
START_CAT = "hajj-health-essentials"
OUTPUT_DIR = "output"
STATE_FILE = "state.json"
BATCH_SIZE = 10000
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
        self.done = set(self.state["done"])
        self.queued = set(self.state["queued"])
        self.total = self.state["total"]
        self.batch_index = self.state["batch_index"]
        self.batch_buffer = []

    def cat_filename(self, cat):
        return os.path.join(OUTPUT_DIR, f"cat_{cat.replace('/', '_')}.jsonl")

    def load_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
        return {"done": [], "queued": [START_CAT], "total": 0, "batch_index": 1}

    def save_state(self, queue):
        with open(STATE_FILE, "w") as f:
            json.dump({
                "done": list(self.done),
                "queued": list(queue),
                "total": self.total,
                "batch_index": self.batch_index,
            }, f)

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

    async def fetch_page(self, proxy_client, cat, page):
        url = BASE_URL + cat
        try:
            response = await proxy_client.get(
                url,
                headers=HEADERS,
                params={"page": page, "limit": PAGE_LIMIT},
            )
            print(f"[HTTP {response.status_code}] {cat} page={page}")
            if response.status_code == 200:
                return response.json()
        except ProxyHTTPError as e:
            print(f"[PROXY ERROR] {cat} page={page} → {type(e).__name__}: {e}")
        except Exception as e:
            print(f"[ERROR] {cat} page={page} → {type(e).__name__}: {e}")
        return None

    def flush_batch(self, force=False):
        while len(self.batch_buffer) >= BATCH_SIZE or (force and self.batch_buffer):
            chunk = self.batch_buffer[:BATCH_SIZE]
            self.batch_buffer = self.batch_buffer[BATCH_SIZE:]
            filename = os.path.join(OUTPUT_DIR, f"products_batch_{self.batch_index}.jsonl")
            with open(filename, "a", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(p, ensure_ascii=False) for p in chunk) + "\n")
            print(f"[BATCH] Wrote {len(chunk)} products → {filename}")
            self.batch_index += 1


    async def process_category(self, proxy_client, cat, queue):
        if cat in self.done:
            print(f"[SKIP] {cat}")
            return

        print(f'CATEGORY:-{cat}')

        data = await self.fetch_page(proxy_client, cat, 1)
        if data is None:
            return

        for code in self.get_child_categories(data):
            if code not in self.done and code not in self.queued:
                self.queued.add(code)
                queue.append(code)

        nb_pages = data.get("nbPages", 1)
        all_hits = data.get("hits", [])

        for page in range(2, nb_pages + 1):
            print(f'Processing page number: {page}')
            import time
            time.sleep(DELAY)
            result = await self.fetch_page(proxy_client, cat, page)
            if result:
                all_hits.extend(result.get("hits", []))

        for h in all_hits:
            h["_category"] = cat
        self.total += len(all_hits)

        print(f"[DONE] {cat:45s} hits={len(all_hits)}  total={self.total}")

        with open(self.cat_filename(cat), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(h, ensure_ascii=False) for h in all_hits) + "\n")
            print('file saved successfully!!')

        self.done.add(cat)
        self.queued.discard(cat)
        self.batch_buffer.extend(all_hits)
        self.flush_batch()


    async def run(self):
        queue = list(self.state["queued"])
        if not queue:
            queue = [START_CAT]

        print(f"Starting — queue={len(queue)}  done={len(self.done)}  saved={self.total}")

        proxy_client = ProxyClient()

        try:
            while queue:
                cat = queue.pop(0)
                if cat in self.done:
                    continue
                await self.process_category(proxy_client, cat, queue)
                self.save_state(queue)
                import time
                time.sleep(DELAY)

        except KeyboardInterrupt:
            print("Interrupted.")
            self.save_state(queue)

        self.flush_batch(force=True)
        self.save_state([])
        print(f"\nDone. Total products: {self.total}  Categories: {len(self.done)}")


if __name__ == "__main__":
    asyncio.run(NoonScraper().run())