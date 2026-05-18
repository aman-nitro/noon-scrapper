import random
from curl_cffi import requests

url = "https://www.noon.com/_vs/nc/mp-customer-catalog-api/api/v3/u/hajj-health-essentials/?f%5BisCarousel%5D=true&isCarouselView=true&productsOnly=true&limit=50"

proxies_list = [
    "brd-customer-hl_444c58d5-zone-proxies_production_3-ip-193.9.56.88:wt9rlxs98lql@brd.superproxy.io:33335",
    "brd-customer-hl_444c58d5-zone-proxies_production_3-ip-193.9.56.173:wt9rlxs98lql@brd.superproxy.io:33335",
    "brd-customer-hl_444c58d5-zone-proxies_production_3-ip-193.9.56.57:wt9rlxs98lql@brd.superproxy.io:33335",
]

def get_proxy():
    raw_proxy = random.choice(proxies_list)

    proxy_url = f"http://{raw_proxy}"

    return {
        "http": proxy_url,
        "https": proxy_url,
    }

headers = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9',
    'referer': 'https://www.noon.com/uae-en/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'x-cms': 'v2',
    'x-platform': 'web',
}

try:
    current_proxy = get_proxy()

    print("Using proxy:", current_proxy["http"])

    response = requests.get(
        url,
        headers=headers,
        proxies=current_proxy,
        impersonate="chrome124",
        timeout=30,
    )

    print("STATUS:", response.status_code)
    print(response.json())
    print(response.text[:1000])

except Exception as e:
    print("Request failed:", str(e))