import json
import threading
import time
import random
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests

class NoonFullCountryMapper:
    def __init__(self):
        self.base_url = "https://www.noon.com"
        self.impersonate = "chrome120"
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "x-platform": "web", "x-locale": "en-ae", "x-mp-country": "ae",
        }

        self.lock = threading.Lock()
        self.discovered_zones = {}
        self.processed_boxes = []
        self.min_box_size = 0.05  # ~5km resolution for final borders
        
        # Shared ThreadPool to prevent recursive overhead
        self.executor = ThreadPoolExecutor(max_workers=10)

    def get_session(self):
        # Create a fresh session for each probe to ensure Akamai cookies are fresh
        s = requests.Session()
        try:
            s.get(f"{self.base_url}/uae-en/", headers=self.headers, impersonate=self.impersonate, timeout=10)
        except:
            pass
        return s

    def probe_coordinate(self, lat, lng):
        session = self.get_session()
        try:
            # 1. Geo Info
            geo_r = session.post(
                f"{self.base_url}/_vs/st/mp-identity-api/serviceable-geo-info/by-location",
                json={"location": {"lat": lat, "lng": lng}},
                headers=self.headers, impersonate=self.impersonate, timeout=10
            )
            geo = geo_r.json()
            if not geo.get("isServiceable"): return None

            # 2. Set Location
            session.post(
                f"{self.base_url}/_vs/st/mp-identity-api/address/set-location",
                json={"location": {"lat": lat, "lng": lng}, "area": geo['area'], "cityId": geo['cityId']},
                headers=self.headers, impersonate=self.impersonate, timeout=10
            )

            # 3. WhoAmI
            who = session.get(f"{self.base_url}/_vs/st/st-whoami-api-web/whoami/noon", 
                              headers=self.headers, impersonate=self.impersonate, timeout=10).json()
            
            wh = who.get("headers", {})
            ecom = wh.get("x-ecom-zonecode")
            rocket = wh.get("x-rocket-zonecode")

            if ecom:
                res = {"ecom": ecom, "rocket": rocket, "area": geo['area'], "lat": lat, "lng": lng}
                with self.lock:
                    if ecom not in self.discovered_zones:
                        self.discovered_zones[ecom] = res
                        print(f"[NEW ZONE] {ecom} | {res['area']} | Rocket: {rocket}")
                return ecom
        except:
            return None

    def scan_recursive(self, b_lat, t_lat, b_lng, t_lng):
        # Check center and corners
        mid_lat, mid_lng = (b_lat + t_lat) / 2, (b_lng + t_lng) / 2
        
        # Probe 5 points in this box
        points = [(b_lat, b_lng), (t_lat, t_lng), (b_lat, t_lng), (t_lat, b_lng), (mid_lat, mid_lng)]
        
        found_zones = set()
        for p in points:
            zone = self.probe_coordinate(p[0], p[1])
            if zone: found_zones.add(zone)

        # If no zones found here, stop exploring this desert/sea box
        if not found_zones:
            return

        # If the box is small enough or uniform, stop
        if (t_lat - b_lat) < self.min_box_size:
            return

        # Otherwise, subdivide into 4 quadrants
        sub_boxes = [
            (b_lat, mid_lat, b_lng, mid_lng),
            (b_lat, mid_lat, mid_lng, t_lng),
            (mid_lat, t_lat, b_lng, mid_lng),
            (mid_lat, t_lat, mid_lng, t_lng)
        ]
        
        futures = [self.executor.submit(self.scan_recursive, *box) for box in sub_boxes]
        for f in futures: f.result()

    def run_uae_wide(self):
        # 1. Define the macro-grid across UAE
        # Dividing UAE into a 10x10 grid to ensure we don't miss isolated towns
        lat_steps = 10
        lng_steps = 10
        
        min_lat, max_lat = 22.5, 26.2
        min_lng, max_lng = 51.5, 56.5
        
        lat_inc = (max_lat - min_lat) / lat_steps
        lng_inc = (max_lng - min_lng) / lng_steps

        print("--- PHASE 1: Initial Macro-Grid Scan ---")
        grid_futures = []
        for i in range(lat_steps):
            for j in range(lng_steps):
                b_lat = min_lat + (i * lat_inc)
                t_lat = b_lat + lat_inc
                b_lng = min_lng + (j * lng_inc)
                t_lng = b_lng + lng_inc
                grid_futures.append(self.executor.submit(self.scan_recursive, b_lat, t_lat, b_lng, t_lng))

        for f in grid_futures:
            f.result()

        print(f"\n--- SCAN COMPLETE: Found {len(self.discovered_zones)} Zones ---")
        with open("noon_uae_full_zones.json", "w") as f:
            json.dump(self.discovered_zones, f, indent=4)

if __name__ == "__main__":
    mapper = NoonFullCountryMapper()
    mapper.run_uae_wide()