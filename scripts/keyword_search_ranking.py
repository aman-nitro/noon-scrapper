import asyncio
import json
import os
import random
import time
from datetime import datetime
from typing import Dict, List, Optional

import aiofiles
import requests  # Clean HTTP/1.1 connection pipeline
from loguru import logger

# ───────────────────────── CONFIG ─────────────────────────

BASE_SEARCH_URL = (
    "https://www.noon.com/_vs/nc/mp-customer-catalog-api"
    "/api/v3/u/search"
)

OUTPUT_DIR = "keyword_rankings"
RESULTS_FILE = os.path.join(OUTPUT_DIR, "rankings.jsonl")

# Your verified, authenticated browser header payload matrix
# FIX: Properly escaped the inner string double quotes on line 35
HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9',
    'baggage': 'sentry-environment=cloudrun,sentry-release=com%404.1.48,sentry-public_key=7b7a99a633ce48be2de6269da900186c,sentry-trace_id=615d5381790942709899e7b59a79bea8,sentry-sample_rate=0.1,sentry-sampled=false',
    'cache-control': 'no-cache, max-age=0, must-revalidate, no-store',
    'pragma': 'no-cache',
    'priority': 'u=1, i',
    'referer': 'https://www.noon.com/uae-en/search/?q=the+hell',
    'sec-ch-ua': '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'sentry-trace': '615d5381790942709899e7b59a79bea8-a5a281695119a704-0',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36',
    'x-border-enabled': 'true',
    'x-cms': 'v2',
    'x-content': 'desktop',
    'x-ecom-zonecode': 'AE_DXB-S14',
    'x-lat': '251051549',
    'x-lng': '552544525',
    'x-locale': 'en-ae',
    'x-mp-country': 'ae',
    'x-platform': 'web',
    'x-rocket-enabled': 'true',
    'x-rocket-zonecode': 'W00068765A',
    'x-visitor-id': '4d8ab649-b3c2-43a3-be65-589b50966789',
    'Cookie': 'visitor_id=4d8ab649-b3c2-43a3-be65-589b50966789; visitorId=4a8e70a4-d0e7-4ebf-bbff-2bf41c03fc32; x-available-ae=ecom; _gcl_au=1.1.2050980866.1778591523; _ga=GA1.1.631087721.1778591523; _fbp=fb.1.1778591523036.977497990819376541; _twpid=tw.1778591523279.976242444686699802; _scid=hPvACi-MoPBJQQyShw58ELEAjIBIGtXS; _pin_unauth=dWlkPU4yVTVOV016TWprdFpqZzVOaTAwWVRaaUxXRTJNMll0TkRnNE5qVmtORGt6TkRVMQ; _tt_enable_cookie=1; _ttp=01KRE51S574Q9GNS41MF38Z8VF_.tt.1; _tt_enable_cookie=1; _ttp=01KRE51S574Q9GNS41MF38Z8VF_.tt.1; _ym_uid=1778591525742665473; _ym_d=1778591525; ZLD887450000000002180avuid=92da6001-d53e-4768-8e4c-50f8dd0b3d86; review_lang=xx; x-available-kw=ecom; ttcsid_D67IF2BC77U7L66NHI00=1778660191917::16R4LsbmNNVgHcqJdhna.1.1778661779201.1; dcae=1; x-available-om=ecom; _clck=1lu3mx7%5E2%5Eg66%5E0%5E2323; _sctr=1%7C1779129000000; ttcsid_D67II9RC77U7623P45E0=1779176479699::Wz7ijADPBm2zykhO2B6-.1.1779176745473.1; x-location-ecom-ae=eyJsYXQiOiAyNTEwNTE1NDksICJsbmciOiA1NTI1NDQ1MjUsICJhcmVhIjogIkR1YmFpIC0gVW5pdGVkIEFyYWIgRW1pcmF0ZXMiLCAiaWRfY2l0eSI6IDF9; nloc=en-ae; bm_ss=ab8e18ef4e; bm_so=F271FA2EFDF0F5744A73C79982B01FB8F2B958F17DA2A1C76A78754F592B1BC0~YAAQ5sIRYBhV9j2eAQAA/kF1QAdy+sprbvmgu3Vf6EwSydGd4pmB7WwhIvsqOIwgC/N6h8oHxQa+cUNNH9MHdqCKxsGzLqDrmeTE6OXzo70rA8UprybyO/8fg0eBQI+YfYPPGaFK1QEr/M55epSZCa1Bc3bI6+QTqdEZ6TKBjr7p6KoSqUkUJLePlpY3vlF/r2qJmU60go/h/buP1s3H9fRSlOi39zVwcIfgfY8TU//IZO5bReP1jzM73JYTfsB4Z0UbkwtPfnysUdrf5U4bziIHiZu5LLNVgrPhHazNJMXMlmlDoUefVXHMhPTZr+LJQuPHoihLAmerFtNquvcrx1dpSrCzzZGxJGtOt40vjH/SKbOkwJ1Eie6mj0tagecacGq6UiE7YSECVdWvVnSi44NOOfvw7VMcatHsKjUYCJyqxPh6ZkIbPpGFKx+Tyc2XuwIX67EFsOV4ArV4R4He; bm_lso=F271FA2EFDF0F5744A73C79982B01FB8F2B958F17DA2A1C76A78754F592B1BC0~YAAQ5sIRYBhV9j2eAQAA/kF1QAdy+sprbvmgu3Vf6EwSydGd4pmB7WwhIvsqOIwgC/N6h8oHxQa+cUNNH9MHdqCKxsGzLqDrmeTE6OXzo70rA8UprybyO/8fg0eBQI+YfYPPGaFK1QEr/M55epSZCa1Bc3bI6+QTqdEZ6TKBjr7p6KoSqUkUJLePlpY3vlF/r2qJmU60go/h/buP1s3H9fRSlOi39zVwcIfgfY8TU//IZO5bReP1jzM73JYTfsB4Z0UbkwtPfnysUdrf5U4bziIHiZu5LLNVgrPhHazNJMXMlmlDoUefVXHMhPTZr+LJQuPHoihLAmerFtNquvcrx1dpSrCzzZGxJGtOt40vjH/SKbOkwJ1Eie6mj0tagecacGq6UiE7YSECVdWvVnSi44NOOfvw7VMcatHsKjUYCJyqxPh6ZkIbPpGFKx+Tyc2XuwIX67EFsOV4ArV4R4He~1779197887011; nguestv2=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJraWQiOiI0Yzg5ZDFiOGNkMDY0YmUyYTBmZmY5N2Y3MzQxMDY1NCIsImlhdCI6MTc3OTE5Nzg4OSwiZXhwIjoxNzc5MTk4MTg5fQ.YKryibTqpezZrYMaNMDXgoc6ixSH2cjZ395WUc1SjU8; nguestv2=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJraWQiOiI0Yzg5ZDFiOGNkMDY0YmUyYTBmZmY5N2Y3MzQxMDY1NCIsImlhdCI6MTc3OTE5Nzg4OSwiZXhwIjoxNzc5MTk4MTg5fQ.YKryibTqpezZrYMaNMDXgoc6ixSH2cjZ395WUc1SjU8; AKA_A2=A; bm_mi=717E0C5579FB1C88D37A0DD0AA0433EB~YAAQ5sIRYMNV9j2eAQAAalJ1QB+X5rWaFSz+5krkSNj/24yayJ9i1B7tf3GlKvJtCCXo2Mz9L6D3zyHjqbdmXdEKRVlMEba1twVdY0/5zEIvbold+pu5fyXah4D87j/R7Df6n5Hd4dCzXVLe9PFGZ92Hlh8OAZnkZaxrcik2t6b9ERAiL2EnD4HZmk8+C9HR/F8CQCBrSmGV3idZgk4Zaa7J6zd0Y4faYx+d4s/n35F7hvzhJ3psW0jkowfwg4rY1jsxciI+0my9unXmVI7VPy1AQ0MaOP+enP3yn9ui7jr5NlG7V1frEdbzGkKJAkKI+X4klz9+AvZOOw==~1; bm_s=YAAQ5sIRYMRV9j2eAQAAalJ1QAXteh9w9+bPobmGuyXKBBpVneRtNpSvXN4j2EeQyFmibDp1A/FmZqWC9mP79m2HoccPXs2vfpcF6PuuC7p6qjMPOfr4Leln+MM6n2Na1KKsc5J0dD14bKqDKsbuxhaz9PnS4t4ixucgne5hyLUU8yACWew4nLgZiroxPHB449UFIX8kfgrcNbRVIkIO0C4AhkC32q7zOrEolGZdqvjmTHf8qMRe7sKVNefSZrnKYESuYIiBQ3LxwBbpg2FMwckxchXjijxs3ge/czmkPgrE3vT8EsQ6Y1VWPxtCR2A1uCn8/LnxIzvgAqfxIVf+8kEK+fso3V3B/09NpJLQq6nL+ppxNtco3vDAvqb2pc9ud5evCSc5RsK6DIBywJ7CtQ8BMgj7ksSdObK13rSpju6AARt+6kgq5wZX1RIKSMpyCOAzr/6VN3B+XZqBa7J33mcjts/BwtYSbv06g86ugJRUhiXq2WQMJLq/bKT60wU6OwjKRmwU2QuM8X7qUKhQCc+WN2muD57vZfIBjCuoXsi63keYJDz5CRCGebroWJah4gSF6tzeXsQbfGUu4cIbTTx+BNv7UuV3ghk7odaTebrCZ6n+MBPE0i8HvjfQBaSG+XMC/drpJtLWlhlyPtmtcgnaxkxRLxZshwfdtdvnAgNhQ0QCnKo2bc7wMdOu0KffxDrwGQnWQLbTpGTiLRJqZeVA4AubY2N322A09idG59YxuqLyw93mwi/WAacj8NM2jDnhBJ2YHc2Bj0nLlvklJYrJd4j4LQrhe3Ey2KGR8RdXCrUWX0WfZ4+CapaE4poBaONy//EDvX99rEATSIDsbqkXIJMBuK5n84yTVs2QF80/vytH2Zx2fwrTueCo8uzqbOk5JrJOciVr5NCQ0z6fSjUkOL+wrQIDzvQUPAY+SwXH/OnTY76asFg=; RT="z=1&dm=noon.com&si=2c31f5a5-7e50-43cf-9825-c4b46a403782&ss=mpck2jyz&sl=0&tt=0&bcn=%2F%2F684d0d43.akstat.io%2F"; x-whoami-data=eyJpc0Nvb2tpZURhdGEiOnRydWUsImhlYWRlcnMiOnsieC1sYXQiOiIyNTEwNTE1NDkiLCJ4LWxuZyI6IjU1MjU0NDUyNSIsIngtYWItdGVzdCI6WzE0NTEsMjc4MSwzNzIyLDEzMzEsMTY1MSwxODMyLDIwNDIsMzc4MSwxNTMxLDI3NTEsMzI3MiwzNzkyLDIyMDEsMjM0MSwzNzExLDI4NDAsMjkwMCwzNTYxLDI0NTEsMzA1MCwzMzYxLDEyNTAsMzE6MiwzMzE1LDQ0NDIsMTg5MSwzODEwLDE3NzEsMjE2MSwyNTYxLDI2OTAsMzQ1MCwxOTYwLDMxNTAsMzI4MSwzMzIxLDMzOTAsMzYxMSwzNjIxLDIyMjIsMTg4MSwyNTMxLDI2MzEsNjcxLDE1ODEsMzUwMSwzNjYwLDI1NDEsMjg5MSwzNTkyLDE5NDEsMzAzMSwzODAwLDMxNDIsMzYzMCwxMTYyLDIyMTIsMjQyNCwzNTMwLDMxODMsMzU3MSwzNjUxLDE0NzEsMzQ5MSwxNzUwLDE5MzEsMjM1MSw4ODEsMjkxMCwyOTQxLDMzNTAsMzQzMSwzNTgxLDY3MSwxMjUwLDI0MjQsMzE1MCwzNDQyLDM1OTIsODgxLDE4MzIsMjkxMCwzMDAxLDM2MjEsMTgwMiwzMjgxLDMzMTUsMzcwMSw0LjEuNDg=; ak_bmsc=C1A79767CEC1F35DCF40ABA55BE6ACDD~000000000000000000000000000000~YAAQ5sIRYPtV9j2eAQAAMld1QB9pqW5cVdTffnWlIZNy0lECPocu2u5tQ0GyOf6HQFfcEFwfvqn+OKQry7MUUzWArqq1IOoEAqR6AN/3j4HRlmxqnsXsqhUmdA21vWRy0QfjM2n0HpTQl1EhaGZ+hzFc0mcdzOVKB9/9XzSr6Aopvv8wRIylm9MLMe+sNbDbvmgMW7mpfAbLamX10vAOYkhbrDtaebRIvQ4keKHqZf6yRK1zygnoxVESCSsFT+pSPV6zvj3lj4QfQDzc9xvV1Jb4vDUR1Aehvm5ScaGAH24nurevoMl5qUxPamN/ufQR2NnB5S1kJ5o/sL8bMGKdAfRUj9xFqV9ix75w5GAVT5S5XCwS5ISbSSwo+uOab3pVl4sTmHF1mfCKItazmSN1A4CtvWZweHCRaz0EWDrQXDOfO0iThY67V0DWTtwrFUkoS6aNT6Omh4mRC8EaODEpAOJ8dB1YD1MfA+i/GfuM5+NlxPsvwZ/AZ8gGA1V6vZgUrI0=; _ga_672ZMW8R4R=GS2.1.s1779195492$o16$g1$t1779197892$j59$l0$h0; _uetsid=3fbdf440528d11f1b91513a8454f8ecb; _uetvid=2aeb52804e0411f1952d6703d8bfc219; ttcsid_CFED02JC77U7HEM9PC8G=1779195490788::bT28vijeY1rRMOej00Fd.9.1779197892675.1; __rtbh.lid=%7B%22eventType%22%3A%22lid%22%2C%22id%22%3A%22UE7g8Sszm3j46THbGnT3%22%2C%22expiryDate%22%3A%222027-05-19T13%3A38%3A12.730Z%22%7D; __rtbh.uid=%7B%22eventType%22%3A%22uid%22%2C%22id%22%3Anull%2C%22expiryDate%22%3A%222027-05-19T13%3A38%3A12.744Z%22%7D; _scid_r=n3vACi-MoPBJQQyShw58ELEAjIBIGtXSQvaJYA; _clsk=8p4hut%5E1779197893534%5E6%5E0%5Ea.clarity.ms%2Fcollect; ttcsid_D778CK3C77U88C4A5SC0=1779195490999::AGjwmlDunuskxm9f6bE2.9.1779197894905.1; ttcsid=1779195484565::SHhTdyfPhChZ37jNvXqR.12.1779197894905.0::1.2404946.2408121::2412870.9.196.22::0.0.0; bm_sv=47BF7D17F24C93743E8045037E14915D~YAAQ5sIRYLtW9j2eAQAAlmt1QB9StQUDgquWi/s1b7m36fLxemJO8uYqR3qgjOQWXXaN7y22Tz22qWnjT4NkU3oPdRsWai1FWCKXpXCVrJQWjfCoi7UM0npXcsG8DElka5Vv0GyghGlOSM0goz1LgJXa+YUMKv+kSPD4Rbh3yvGXkYsi9oP2SVEWFuUljdvRnp9D5/V+/eZg6cSLn8AGR5Oe1gMItm6q58oCu8QJNy/xmR6sN/UWq/0T6HMm7Q==~1; bm_sv=47BF7D17F24C93743E8045037E14915D~YAAQ1wFAF1sI8B+eAQAALJx1QB9GiTVLk9+WOjCXzjpIdCUpG19K3ebEws9XlxaurzgxyMSUFiANNI89SiChVfM22sgrQStJCs2CmqccXHVgWgyzvEbNN5jLE1FVIv4LGYV2BG3cx41UaZeroxva89YEJZiSShkxewhBkNLCvm2rh+8q6yaxMjCsyWuQzEHxBXoFoIvwEau7aQaF2Y6mk1Bhqib9N/5pL9VG6lfirTik4DL41XDwKdzn3B66kA==~1; dcae=2; nguestv2=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJraWQiOiI0Yzg5ZDFiOGNkMDY0YmUyYTBmZmY5N2Y3MzQxMDY1NCIsImlhdCI6MTc3OTExMjE0MSwiZXhwIjoxYzc5MTEyNDQxfQ.h4kDbpjXQt8A_v1hMDup_WsxKTXXBFR0btSO7AvA7vY; x-available-ae=ecom; x-location-ecom-ae=eyJsYXQiOiAyNDMzNTA4OTUsICJsbmciOiA1NDUyNDMwMjIsICJhcmVhIjogIklDQUQgSSIsICJpZF9jaXR5IjogMn0='
}

# ───────────────────────── SEARCH EXECUTOR ─────────────────────────

def run_sync_request(params: dict) -> Optional[dict]:
    """Runs a standard sequential HTTP/1.1 request via requests inside a thread worker."""
    try:
        response = requests.get(
            url=BASE_SEARCH_URL,
            headers=HEADERS,
            params=params,
            timeout=15
        )
        if response.status_code == 200:
            return response.json()
        logger.warning(f"[HTTP {response.status_code}] Dropped by backend validation.")
        return None
    except Exception as e:
        logger.error(f"[REQUEST EXCEPTION] Thread worker pipeline failed -> {e}")
        return None

async def search_keyword(keyword: str, page: int = 1, limit: int = 50) -> Optional[Dict]:
    params = {
        "q": keyword,
        "page": page,
        "limit": limit,
    }
    logger.debug(f"[SEARCH] Indexing catalog targets for keyword='{keyword}' │ page={page}")
    
    return await asyncio.to_thread(run_sync_request, params)

# ───────────────────────── PARSER & EXTRACTION ─────────────────────────

def extract_rankings(keyword: str, search_data: Dict, page: int = 1) -> List[Dict]:
    rankings = []
    hits = search_data.get("hits", [])

    for idx, product in enumerate(hits, start=1):
        global_rank = ((page - 1) * 50) + idx

        rank_data = {
            "timestamp": datetime.now().isoformat(),
            "keyword": keyword,
            "page": page,
            "position_on_page": idx,
            "global_rank": global_rank,
            "product_id": product.get("id"),
            "product_name": product.get("title") or product.get("name"), 
            "product_sku": product.get("sku"),
            "brand": product.get("brand") or product.get("brand_name"),
            "price": product.get("price"),
            "original_price": product.get("original_price"),
            "discount_percent": product.get("discount_percent"),
            "rating": product.get("rating") or product.get("average_rating"),
            "review_count": product.get("review_count"),
            "in_stock": product.get("is_in_stock") or product.get("in_stock"),
            "url": product.get("url"),
        }
        rankings.append(rank_data)

    return rankings

async def save_ranking(rank_data: Dict) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    async with aiofiles.open(RESULTS_FILE, "a", encoding="utf-8") as f:
        await f.write(json.dumps(rank_data, ensure_ascii=False) + "\n")

def print_rankings_summary(keyword: str, rankings: List[Dict], total_hits: int, total_pages: int) -> None:
    print(f"\n{'=' * 80}")
    print(f"SEARCH RANKING MATRIX: {keyword.upper()}")
    print(f"{'=' * 80}")
    print(f"Total Hits: {total_hits:,} │ Total Pages: {total_pages} │ Tracked: {len(rankings)}")
    print(f"{'-' * 80}")
    print(f"{'Rank':<6} {'Brand':<20} {'Product Name':<35} {'Price'}")
    print(f"{'-' * 80}")

    for rank in rankings[:10]:
        name = rank["product_name"][:32] if rank.get("product_name") else "N/A"
        brand = rank["brand"][:17] if rank.get("brand") else "N/A"
        price = f"AED {rank['price']}" if rank.get("price") else "N/A"
        print(f"{rank['global_rank']:<6} {brand:<20} {name:<35} {price}")
    print(f"{'=' * 80}\n")

# ───────────────────────── MAIN ENGINE RUNNER ─────────────────────────

async def main():
    logger.info("Initializing stable sequential HTTP/1.1 keyword tracking engine...")
    keywords = ["iphone", "samsung", "macbook"]

    for keyword in keywords:
        search_data = await search_keyword(keyword=keyword, page=1)
        if not search_data:
            logger.error(f"Timeline indexing skipped for vector: '{keyword}' due to connection drops.")
            continue

        total_hits = search_data.get("nbHits") or search_data.get("total_products") or 0
        total_pages = search_data.get("nbPages") or 1

        rankings = extract_rankings(keyword=keyword, search_data=search_data, page=1)
        
        for rank in rankings:
            await save_ranking(rank)

        print_rankings_summary(keyword, rankings, total_hits, total_pages)
        
        # Human mimic pacing delay between targets
        sleep_duration = random.uniform(2.5, 4.0)
        logger.info(f"Target vector complete. Pacing channel sleeping for {sleep_duration:.2f}s...")
        await asyncio.sleep(sleep_duration)

    logger.success(f"Tracking run complete! Data mapped into JSON Lines directly -> {RESULTS_FILE}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[RUN INTERRUPTED]")