import asyncio
import json
import os
import sys
import time
import uuid
from typing import Dict, List, Optional

from loguru import logger
from curl_cffi.requests import AsyncSession

# Fix system pathing
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)) + "/..")

from proxy.proxy_manager import ProxyManager, ProxyConfig
from proxy.proxy_client import ProxyClient
from proxy.proxies import proxy_urls 

# ============================================================
# CONFIG
# ============================================================

OUTPUT_FILE = "warehouses.json"
MAX_CONCURRENT = 15  # Low concurrency ensures Akamai doesn't trigger bot protection

GEO_URL = "https://www.noon.com/_vs/st/mp-identity-api/serviceable-geo-info/by-location"
WHOAMI_URL = "https://www.noon.com/_vs/st/st-whoami-api-web/whoami/noon"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": "https://www.noon.com",
    "referer": "https://www.noon.com/uae-en/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "x-platform": "web", "x-locale": "en-ae", "x-mp-country": "ae",
}

# Targeted residential corridors
URBAN_BOXES = [
    {
        "name": "Dubai - Sharjah - Ajman Metro Area",
        "min_lat": 24.95, "max_lat": 25.55,
        "min_lng": 54.95, "max_lng": 55.60
    },
    {
        "name": "Abu Dhabi Metro Sprawl",
        "min_lat": 24.25, "max_lat": 24.60,
        "min_lng": 54.30, "max_lng": 54.75
    },
    {
        "name": "Al Ain Hub Area",
        "min_lat": 24.05, "max_lat": 24.30,
        "min_lng": 55.60, "max_lng": 55.85
    }
]

# ============================================================
# FETCH PIPELINE (Isolated Session Lifecycle)
# ============================================================

async def fetch_warehouse(client: ProxyClient, lat: float, lng: float) -> Optional[Dict]:
    owner_id = f"client-{uuid.uuid4().hex[:6]}"
    proxy = client.manager.reserve_proxy(owner_id)
    if not proxy:
        return None

    proxies_dict = client._get_proxies_dict(proxy)
    curl_opts = client._get_curl_resolve_options(proxy)

    try:
        # CRITICAL FIX: Every worker gets a completely isolated, locked session instance
        async with AsyncSession(
            impersonate="chrome120",
            timeout=30,
            curl_options=curl_opts
        ) as session:
            
            # STEP 1: Verify coordinate serviceability
            geo_response = await session.post(
                url=GEO_URL,
                json={"location": {"lat": lat, "lng": lng}},
                headers=HEADERS,
                proxies=proxies_dict
            )

            if geo_response.status_code != 200:
                client.manager.release_proxy(proxy.id)
                return None

            geo_data = geo_response.json()
            area_value = geo_data.get("area") or geo_data.get("placeName") or f"Lat:{lat}_Lng:{lng}"
            city_id_value = geo_data.get("cityId") or 1

            # STEP 2: Force location updates onto this specific, isolated cookie jar
            set_loc_payload = {
                "location": {"lat": lat, "lng": lng},
                "area": area_value,
                "cityId": city_id_value
            }

            set_loc_response = await session.post(
                url="https://www.noon.com/_vs/st/mp-identity-api/address/set-location",
                json=set_loc_payload,
                headers=HEADERS,
                proxies=proxies_dict
            )

            if set_loc_response.status_code != 200:
                client.manager.release_proxy(proxy.id)
                return None

            # Small sleep mimics real user pacing so Noon doesn't flag the request sequence
            await asyncio.sleep(0.5)

            # STEP 3: Grab unique tracking warehouse codes from session context
            whoami_response = await session.get(
                url=WHOAMI_URL,
                headers=HEADERS,
                proxies=proxies_dict
            )

            if whoami_response.status_code != 200:
                client.manager.release_proxy(proxy.id)
                return None

            whoami_data = whoami_response.json()
            resp_headers = whoami_data.get("headers", {})
            
            ecom_zone = resp_headers.get("x-ecom-zonecode")
            rocket_zone = resp_headers.get("x-rocket-zonecode")

            if isinstance(ecom_zone, list) and ecom_zone: ecom_zone = ecom_zone[0]
            if isinstance(rocket_zone, list) and rocket_zone: rocket_zone = rocket_zone[0]

            if not ecom_zone: ecom_zone = whoami_response.headers.get("x-ecom-zonecode")
            if not rocket_zone: rocket_zone = whoami_response.headers.get("x-rocket-zonecode")

            if not ecom_zone:
                client.manager.release_proxy(proxy.id)
                return None

            logger.success(f"[SUCCESS] Discovered Hub: {ecom_zone} -> {area_value}")
            client.manager.mark_success(proxy.id)
            
            return {
                "warehouse_key": ecom_zone,
                "ecom": ecom_zone,
                "rocket": rocket_zone if rocket_zone else None,
                "area": area_value,
                "lat": lat,
                "lng": lng
            }

    except Exception:
        client.manager.release_proxy(proxy.id)
        return None

# ============================================================
# SEMAPHORE BOUND WORKER
# ============================================================

async def worker(semaphore: asyncio.Semaphore, client: ProxyClient, lat: float, lng: float) -> Optional[Dict]:
    async with semaphore:
        return await fetch_warehouse(client, lat, lng)

# ============================================================
# MAIN ENGINE
# ============================================================

async def main():
    logger.info("Initializing isolated-session warehouse scroller...")
    started = time.time()

    config = ProxyConfig()
    proxy_manager = ProxyManager(config=config, platform="noon")
    
    raw_proxies = []
    for values in proxy_urls.values():
        if values: raw_proxies.extend(values)
    proxy_manager.load_proxies_from_url_list(raw_proxies)

    client = ProxyClient(config=config, proxy_manager=proxy_manager)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    # 0.1km increments balances speed and coverage density
    step = 0.001 
    tasks = []

    for box in URBAN_BOXES:
        curr_lat = box["min_lat"]
        while curr_lat <= box["max_lat"]:
            curr_lng = box["min_lng"]
            while curr_lng <= box["max_lng"]:
                tasks.append(
                    asyncio.create_task(
                        worker(semaphore, client, round(curr_lat, 4), round(curr_lng, 4))
                    )
                )
                curr_lng += step
            curr_lat += step

    logger.info(f"Loaded {len(tasks)} coordinates into safe loop runner.")

    # Execute and wait for results array
    raw_results = await asyncio.gather(*tasks)
    elapsed = time.time() - started

    # Deduplicate matching keys cleanly
    final_dictionary_map = {}
    for item in raw_results:
        if item and "warehouse_key" in item:
            w_key = item["warehouse_key"]
            final_dictionary_map[w_key] = item

    with open(OUTPUT_FILE, "w") as f:
        json.dump(final_dictionary_map, f, indent=4)

    await client.close_all_sessions()

    logger.info("══════════════════════════════")
    logger.info("WAREHOUSE SCROLLER COMPLETE")
    logger.info(f"Total Grid Nodes Checked={len(tasks)}")
    logger.info(f"Unique Active Warehouses Extracted={len(final_dictionary_map)}")
    logger.info(f"Saved directly to file={OUTPUT_FILE}")
    logger.info(f"Total Execution Time={elapsed:.2f}s")
    logger.info("══════════════════════════════")

if __name__ == "__main__":
    asyncio.run(main())