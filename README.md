# 🛒 Noon Scraper

A high-performance, async-first web scraper for [Noon.com](https://www.noon.com) (UAE) that crawls the full product catalog, resolves location-based inventory per zone, and maps every Noon warehouse/delivery zone across the UAE.

---

## 📌 Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Features](#features)
- [How It Works](#how-it-works)
- [Setup & Usage](#setup--usage)
- [Configuration](#configuration)
- [Output Files](#output-files)
- [Metrics Dashboard](#metrics-dashboard)
- [Notes & Caveats](#notes--caveats)

---

## Overview

Noon Scraper is a Python toolkit that:

1. **Crawls the full Noon.com product catalog** starting from any category (e.g. `hajj-health-essentials`) and recursively discovers all child categories via Noon's internal catalog API.
2. **Scrapes product data** (name, price, availability, seller, SKU, rocket status, etc.) and saves it as batched JSONL files.
3. **Resolves location-specific inventory** — queries Noon's identity + whoami APIs to simulate being in a specific UAE city/area and fetches location-aware product listings.
4. **Maps all Noon delivery zones/warehouses** across the UAE using a recursive spatial subdivision algorithm (adaptive quad-tree scanning).

---

## Project Structure

```
noon-scrapper/
│
├── main.py                        # Synchronous crawler (requests + BFS queue, resumable)
├── noon.py                        # Async crawler (aiohttp, concurrent, batch output)
├── location.py                    # Location resolver + inventory diff across UAE cities
├── state.json                     # Persistent crawl state (visited, queue, total)
│
├── constants/
│   ├── noon_category.py           # Full Noon.com category map (100+ categories)
│   └── noon_warehouses.py         # Discovered warehouse/zone map (ecom + rocket codes)
│
├── scripts/
│   └── fetch_warehouses.py        # UAE-wide zone discovery via adaptive quad-tree probe
│
├── proxy/
│   ├── proxies.py                 # Proxy list definitions
│   ├── proxy_client.py            # HTTP client with proxy rotation
│   └── proxy_manager.py          # Proxy pool management & health tracking
│
├── output/
│   ├── cat_<category>.jsonl       # Per-category product dumps
│   └── products_batch_<N>.jsonl  # Batched product files (10,000 products/file)
│
└── tests/
    └── test.py                    # Test suite
```

---

## Features

| Feature | Details |
|---|---|
| **Async Scraping** | `noon.py` uses `aiohttp` with configurable concurrency (default: 10 workers) |
| **Resumable Crawls** | State is saved to `state.json` after every category — restart anytime and it picks up where it left off |
| **Batched Output** | Products flushed in 10,000-record JSONL batches to avoid memory issues |
| **Per-Category Files** | Each category also gets its own `cat_<name>.jsonl` for granular inspection |
| **Location-Aware Scraping** | `location.py` resolves zone headers (ecom/rocket codes) per GPS coordinate to fetch location-specific stock |
| **Inventory Diff** | Compares product availability, price, and rocket status across multiple UAE locations |
| **Warehouse Zone Mapper** | `fetch_warehouses.py` discovers all ecom + rocket zones by probing a 10×10 GPS grid over UAE with recursive subdivision |
| **100+ Category Map** | `constants/noon_category.py` has pre-mapped slugs across Electronics, Fashion, Home, Grocery, Baby, Health, and more |
| **16 Known Warehouses** | `constants/noon_warehouses.py` contains pre-discovered UAE zone codes with GPS and area metadata |
| **Proxy Support** | Full proxy rotation infrastructure in `proxy/` for high-volume scraping |

---

## How It Works

### 1. Product Catalog Crawl (`noon.py` / `main.py`)

```
START_CAT (e.g. "hajj-health-essentials")
    │
    ▼
Fetch page 1 of category via Noon's internal catalog API
    │
    ├─► Parse `facets[code=category]` tree → discover child category slugs
    │       └─► Enqueue all new child categories
    │
    ├─► Save all `hits` (products) from this category
    │       └─► Flush to batched JSONL when buffer hits 10,000
    │
    ├─► Paginate remaining pages (up to nbPages)
    │
    └─► Mark category as visited → save state → move to next
```

- **API endpoint:** `https://www.noon.com/_vs/nc/mp-customer-catalog-api/api/v3/u/<category-slug>`
- **Pagination:** `?page=N&limit=50`
- **State:** Stored in `state.json` with `visited`, `queue`, `total`, and `batch_index`

### 2. Location-Aware Inventory (`location.py`)

For each configured GPS coordinate (e.g. Dubai Marina, Al Warqa, Abu Dhabi):

1. `POST /serviceable-geo-info/by-location` — checks if the location is serviceable, returns `area` + `cityId`
2. `POST /address/set-location` — sets the session's delivery location
3. `GET /whoami/noon` — returns resolved zone headers: `x-ecom-zonecode`, `x-rocket-zonecode`
4. Fetch product listings using those zone headers
5. Build an **inventory matrix** (SKU → location → {price, availability, seller, rocket})
6. Print inventory **diffs** — which SKUs appear/disappear or change price across locations

### 3. Warehouse Zone Discovery (`scripts/fetch_warehouses.py`)

- Divides UAE bounding box (`lat: 22.5–26.2`, `lng: 51.5–56.5`) into a **10×10 macro-grid**
- For each grid cell, probes 5 GPS points (corners + center)
- If a new zone is found, **recursively subdivides** the cell into 4 quadrants (adaptive quad-tree)
- Stops subdividing when the cell is `< 0.05°` (~5 km) or is uninhabited/non-serviceable
- Uses **10 parallel threads** via `ThreadPoolExecutor`
- Saves results to `noon_uae_full_zones.json`

---

## Setup & Usage

### Requirements

```bash
pip install requests aiohttp aiofiles curl_cffi
```

### Run the Async Crawler (Recommended)

```bash
python noon.py
```

- Starts from `START_CAT = "hajj-health-essentials"` (configurable in `noon.py`)
- Saves output to `output/` directory
- Resumes automatically if `state.json` exists

### Run the Sync Crawler

```bash
python main.py
```

- Simpler, single-threaded version; useful for debugging
- Saves to `products.jsonl` in the project root

### Resolve Location-Based Inventory

```bash
python location.py
```

- Edit the `LOCATIONS` list and `CATEGORY_API` URL at the top to customize
- Prints inventory differences across configured locations

### Discover UAE Warehouse Zones

```bash
python scripts/fetch_warehouses.py
```

- Requires `curl_cffi` (handles Akamai bot protection)
- Outputs `noon_uae_full_zones.json`

---

## Configuration

### Key Constants (`noon.py`)

| Variable | Default | Description |
|---|---|---|
| `START_CAT` | `hajj-health-essentials` | Root category to begin crawling |
| `OUTPUT_DIR` | `output/` | Directory for JSONL output files |
| `STATE_FILE` | `state.json` | Crawl state persistence file |
| `BATCH_SIZE` | `10000` | Products per batch JSONL file |
| `CONCURRENCY` | `10` | Async HTTP worker count |
| `PAGE_LIMIT` | `50` | Products per API page (Noon's max) |
| `DELAY` | `0.4s` | Polite delay between requests |

### Authentication

Noon's API requires a valid session **cookie**. Update the `COOKIE` constant at the top of `main.py` / `noon.py` when it expires:

```python
COOKIE = "ak_bmsc=...;  bm_sv=...; nguestv2=...; ..."
```

> **Tip:** Grab fresh cookies from your browser's DevTools (Network tab) after visiting `noon.com`. The `nguestv2` JWT token typically expires every 5 minutes, while `ak_bmsc`/`bm_sv` (Akamai) cookies last longer.

### Zone Header

The `x-ecom-zonecode` header controls which warehouse serves the request. See `constants/noon_warehouses.py` for all known zone codes. Default: `AE_DXB-S14` (Dubai).

---

## Output Files

### `output/products_batch_<N>.jsonl`
Batched product records. Each line is a JSON object:

```json
{
  "sku": "Z123456AE",
  "name": "Centrum Multivitamin 100 Tablets",
  "brand": "Centrum",
  "salePrice": 49.0,
  "price": 65.0,
  "isOutOfStock": false,
  "isRocket": true,
  "sellerName": "Noon",
  "_category": "health/vitamins-and-dietary-supplements/vitamins/multivitamins-noon"
}
```

### `output/cat_<category-slug>.jsonl`
Same structure but scoped to a single category — useful for targeted analysis.

### `state.json`
```json
{
  "visited": ["hajj-health-essentials", "health", ...],
  "queue": ["home-and-kitchen", ...],
  "total": 10399,
  "batch_index": 2
}
```

---

## Metrics Dashboard

Open [`dashboard.html`](./dashboard.html) in your browser for a live visual summary of the scrape, including:

- 📦 Total products scraped
- 🗂️ Categories visited vs. queued
- 🏭 Warehouse zones (ecom + rocket)
- 📁 Output batch files & sizes
- 🗺️ Known UAE delivery zones

The dashboard reads from `state.json` and `constants/noon_warehouses.py` (embedded at build time).

---

## Notes & Caveats

- **Cookie Rotation:** Noon uses Akamai bot-detection. Cookies expire frequently. The `proxy/` module and `curl_cffi` (in `fetch_warehouses.py`) help mitigate this.
- **Rate Limiting:** A `DELAY` of 0.4–0.6s is baked in. Decrease at your own risk.
- **Geo-Fenced Inventory:** Prices and availability genuinely differ by zone. Use `location.py` to study these differences.
- **Resumability:** Always safe to `Ctrl+C` — state is checkpointed after every category.
- **Legal:** This tool is for research and analysis. Always respect `robots.txt` and Noon's Terms of Service.