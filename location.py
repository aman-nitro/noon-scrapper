import requests
import json
import time
from collections import defaultdict

BASE_URL = "https://www.noon.com"

session = requests.Session()

COMMON_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "accept": "application/json, text/plain, */*",
    "x-platform": "web",
    "x-content": "desktop",
    "x-cms": "v2",
    "x-locale": "en-ae",
    "x-mp-country": "ae",
}


# -------------------------------------------------------------------
# STEP 1: LOCATIONS YOU WANT TO TEST
# -------------------------------------------------------------------

LOCATIONS = [
    {
        "name": "Dubai Marina",
        "lat": 25.0800,
        "lng": 55.1400,
    },
    {
        "name": "Al Warqa",
        "lat": 25.1834186,
        "lng": 55.4490844,
    },
    {
        "name": "Abu Dhabi",
        "lat": 24.3350895,
        "lng": 54.5243022,
    },
]


# -------------------------------------------------------------------
# STEP 2: CATEGORY API
# -------------------------------------------------------------------

CATEGORY_API = (
    "https://www.noon.com/_vs/nc/mp-customer-catalog-api/api/v3/u/"
    "electronics-and-mobiles/television-and-video"
)


# -------------------------------------------------------------------
# STEP 3: RESOLVE LOCATION
# -------------------------------------------------------------------

def resolve_location(lat, lng):
    """
    Calls:
    /by-location
    /set-location
    /whoami

    Returns:
    operational headers/context
    """

    # ---------------------------------------------------------------
    # by-location
    # ---------------------------------------------------------------

    by_location_url = (
        f"{BASE_URL}/_vs/st/mp-identity-api/serviceable-geo-info/by-location"
    )

    payload = {
        "location": {
            "lat": lat,
            "lng": lng,
        }
    }

    r = session.post(
        by_location_url,
        headers=COMMON_HEADERS,
        json=payload,
        timeout=30,
    )

    r.raise_for_status()

    geo = r.json()

    if not geo.get("isServiceable"):
        raise Exception(f"Location not serviceable: {lat}, {lng}")

    # ---------------------------------------------------------------
    # set-location
    # ---------------------------------------------------------------

    set_location_url = (
        f"{BASE_URL}/_vs/st/mp-identity-api/address/set-location"
    )

    set_payload = {
        "location": {
            "lat": lat,
            "lng": lng,
        },
        "area": geo.get("area"),
        "cityId": geo.get("cityId"),
    }

    r = session.post(
        set_location_url,
        headers=COMMON_HEADERS,
        json=set_payload,
        timeout=30,
    )

    r.raise_for_status()

    # ---------------------------------------------------------------
    # whoami
    # ---------------------------------------------------------------

    whoami_url = (
        f"{BASE_URL}/_vs/st/st-whoami-api-web/whoami/noon"
    )

    r = session.get(
        whoami_url,
        headers=COMMON_HEADERS,
        timeout=30,
    )

    r.raise_for_status()

    whoami = r.json()

    headers = whoami.get("headers", {})

    return {
        "geo": geo,
        "whoami": whoami,
        "headers": {
            "x-ecom-zonecode": headers.get("x-ecom-zonecode"),
            "x-rocket-zonecode": headers.get("x-rocket-zonecode"),
            "x-rocket-enabled": str(
                headers.get("x-rocket-enabled", "false")
            ).lower(),
            "x-lat": str(int(lat * 1e7)),
            "x-lng": str(int(lng * 1e7)),
        }
    }


# -------------------------------------------------------------------
# STEP 4: FETCH PRODUCTS
# -------------------------------------------------------------------

def fetch_products(location_ctx, limit=100):

    headers = COMMON_HEADERS.copy()

    headers.update(location_ctx["headers"])

    params = {
        "limit": limit,
    }

    r = session.get(
        CATEGORY_API,
        headers=headers,
        params=params,
        timeout=30,
    )

    r.raise_for_status()

    data = r.json()

    # DEBUG
    print("\n==========================")
    print("ZONE:", headers["x-ecom-zonecode"])
    print("ROCKET:", headers["x-rocket-zonecode"])
    print("==========================")

    # Noon APIs vary.
    # Try multiple possible keys.

    products = []

    if "hits" in data:
        products = data["hits"]

    elif "products" in data:
        products = data["products"]

    elif "catalog" in data:
        products = data["catalog"].get("products", [])

    return products


# -------------------------------------------------------------------
# STEP 5: COMPARE INVENTORY
# -------------------------------------------------------------------

inventory_matrix = defaultdict(dict)

for loc in LOCATIONS:

    print(f"\nResolving location: {loc['name']}")

    try:

        ctx = resolve_location(
            lat=loc["lat"],
            lng=loc["lng"],
        )

        print(json.dumps(ctx["headers"], indent=2))

        products = fetch_products(ctx)

        print(f"Fetched {len(products)} products")

        for p in products:

            sku = (
                p.get("sku")
                or p.get("skuCode")
                or p.get("id")
            )

            if not sku:
                continue

            inventory_matrix[sku][loc["name"]] = {
                "name": p.get("name"),
                "price": (
                    p.get("salePrice")
                    or p.get("price")
                ),
                "available": not p.get("isOutOfStock", False),
                "seller": p.get("sellerName"),
                "rocket": (
                    p.get("isRocket")
                    or p.get("rocket")
                ),
            }

        time.sleep(2)

    except Exception as e:
        print(f"ERROR for {loc['name']}: {e}")


# -------------------------------------------------------------------
# STEP 6: PRINT INVENTORY DIFFERENCES
# -------------------------------------------------------------------

print("\n\n==========================")
print("INVENTORY DIFFERENCES")
print("==========================")

for sku, locations in inventory_matrix.items():

    if len(locations) <= 1:
        continue

    print("\n--------------------------------")
    print("SKU:", sku)

    for loc_name, data in locations.items():

        print(
            f"{loc_name}: "
            f"available={data['available']} | "
            f"price={data['price']} | "
            f"rocket={data['rocket']} | "
            f"name={data['name'][:60]}"
        )