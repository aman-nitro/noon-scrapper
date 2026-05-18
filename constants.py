import os

NOON_PG_DATABASE_URL = os.getenv(
    "NOON_PG_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@noon_pg:5432/noon_pg")
NOON_REDIS_DB = os.getenv("NOON_REDIS_DB", "0")
NOON_REDIS_HOST = os.getenv("NOON_REDIS_HOST", "redis")
NOON_REDIS_PORT = int(os.getenv("NOON_REDIS_PORT", 6679))
NOON_REDIS_PASSWORD = os.getenv("NOON_REDIS_PASSWORD", "")


NOON_BASE_URL = 'https://www.noon.com/_vs/nc/mp-customer-catalog-api/api/v3/u'


NOON_WAREHOUSE = {
    "AE_AUH-S11": {
        "ecom": "AE_AUH-S11",
        "rocket": None,
        "area": "Um Laylah",
        "lat": 24.0,
        "lng": 54.0
    },
    "AE_AUH-S13": {
        "ecom": "AE_AUH-S13",
        "rocket": None,
        "area": "Um Laylah",
        "lat": 24.0,
        "lng": 54.1
    },
    "AE_AUH-S5": {
        "ecom": "AE_AUH-S5",
        "rocket": None,
        "area": "U35",
        "lat": 24.0,
        "lng": 54.80000000000001
    },
    "AE_AAN-S4": {
        "ecom": "AE_AAN-S4",
        "rocket": None,
        "area": "Mghayel Bin Omeir",
        "lat": 24.0,
        "lng": 54.90000000000001
    },
    "AE_AAN-S3": {
        "ecom": "AE_AAN-S3",
        "rocket": None,
        "area": "Lubnan",
        "lat": 24.0,
        "lng": 55.100000000000016
    },
    "AE_AAN-S2": {
        "ecom": "AE_AAN-S2",
        "rocket": None,
        "area": "Um Ghaffa",
        "lat": 24.1,
        "lng": 55.90000000000003
    },
    "AE_AUH-S4": {
        "ecom": "AE_AUH-S4",
        "rocket": None,
        "area": "Mafraq Industrial Area",
        "lat": 24.300000000000004,
        "lng": 54.60000000000001
    },
    "AE_AUH-S7": {
        "ecom": "AE_AUH-S7",
        "rocket": None,
        "area": "Al Haffar",
        "lat": 24.300000000000004,
        "lng": 54.80000000000001
    },
    "AE_AAN-S1": {
        "ecom": "AE_AAN-S1",
        "rocket": None,
        "area": "Al Ain, Abu Dhabi, United Arab Emirates",
        "lat": 24.300000000000004,
        "lng": 55.50000000000002
    },
    "AE_AUH-S1": {
        "ecom": "AE_AUH-S1",
        "rocket": "W00835102AE",
        "area": "Al Hudayriat Island",
        "lat": 24.400000000000006,
        "lng": 54.400000000000006
    },
    "AE_AUH-S17": {
        "ecom": "AE_AUH-S17",
        "rocket": "W00835102AE",
        "area": "MQ6",
        "lat": 24.400000000000006,
        "lng": 54.50000000000001
    },
    "AE_AUH-S6": {
        "ecom": "AE_AUH-S6",
        "rocket": None,
        "area": "MZ28",
        "lat": 24.400000000000006,
        "lng": 54.60000000000001
    },
    "AE_AUH-S8": {
        "ecom": "AE_AUH-S8",
        "rocket": None,
        "area": "Abu Dhabi, United Arab Emirates",
        "lat": 24.400000000000006,
        "lng": 54.90000000000001
    },
    "AE_AUH-S2": {
        "ecom": "AE_AUH-S2",
        "rocket": "W00835102AE",
        "area": "RT4",
        "lat": 24.500000000000007,
        "lng": 54.400000000000006
    },
    "AE_DXB-S4": {
        "ecom": "AE_DXB-S4",
        "rocket": None,
        "area": "Community Hefair",
        "lat": 24.70000000000001,
        "lng": 55.20000000000002
    },
    "AE_DXB-S14": {
        "ecom": "AE_DXB-S14",
        "rocket": "W00068765A",
        "area": None,
        "lat": 24.70000000000001,
        "lng": 56.30000000000003
    }
}

# noon_categories.py - Comprehensive Noon.com Category List

NOON_CATEGORIES = {
    # === ELECTRONICS & MOBILES ===
    "smartphones": "electronics-and-mobiles/mobiles-and-accessories/smartphones",
    "mobile_accessories": "electronics-and-mobiles/mobiles-and-accessories/mobile-accessories",
    "laptops": "electronics-and-mobiles/computers-laptops/laptops",
    "tablets": "electronics-and-mobiles/computers-laptops/tablets",
    "computer_accessories": "electronics-and-mobiles/computers-laptops/computer-accessories",
    "headphones": "electronics-and-mobiles/audio-video/headphones-headsets",
    "speakers": "electronics-and-mobiles/audio-video/speakers",
    "smartwatches": "electronics-and-mobiles/wearable-technology/smartwatches",
    "fitness_trackers": "electronics-and-mobiles/wearable-technology/fitness-trackers",
    "cameras": "electronics-and-mobiles/cameras-camcorders/digital-cameras",
    "camera_accessories": "electronics-and-mobiles/cameras-camcorders/camera-accessories",
    "tvs": "electronics-and-mobiles/televisions-projectors/televisions",
    "tv_accessories": "electronics-and-mobiles/televisions-projectors/tv-video-accessories",
    "gaming_consoles": "electronics-and-mobiles/video-games/video-game-consoles",
    "video_games": "electronics-and-mobiles/video-games/video-games",
    "gaming_accessories": "electronics-and-mobiles/video-games/video-game-accessories",
    
    # === HOME & KITCHEN ===
    "home_appliances": "home-kitchen/home-appliances",
    "kitchen_appliances": "home-kitchen/kitchen-dining/kitchen-appliances",
    "cookware": "home-kitchen/kitchen-dining/cookware",
    "tableware": "home-kitchen/kitchen-dining/tableware-dinnerware",
    "home_decor": "home-kitchen/home-decor",
    "furniture": "home-kitchen/furniture",
    "bedding": "home-kitchen/bedding-bath/bedding",
    "bath": "home-kitchen/bedding-bath/bath",
    "storage": "home-kitchen/home-organization/storage-organization",
    "lighting": "home-kitchen/lighting",
    
    # === FASHION ===
    "mens_clothing": "mens-fashion/mens-clothing",
    "mens_shoes": "mens-fashion/mens-shoes",
    "mens_accessories": "mens-fashion/mens-accessories",
    "womens_clothing": "womens-fashion/womens-clothing",
    "womens_shoes": "womens-fashion/womens-shoes",
    "womens_accessories": "womens-fashion/womens-accessories",
    "womens_bags": "womens-fashion/womens-bags-luggage",
    "kids_clothing": "kids-fashion/kids-clothing",
    "kids_shoes": "kids-fashion/kids-shoes",
    
    # === BEAUTY & FRAGRANCE ===
    "makeup": "beauty-fragrance/makeup",
    "skincare": "beauty-fragrance/skin-care",
    "haircare": "beauty-fragrance/hair-care",
    "fragrances": "beauty-fragrance/fragrances",
    "beauty_tools": "beauty-fragrance/beauty-tools-accessories",
    "mens_grooming": "beauty-fragrance/mens-grooming",
    
    # === BABY ===
    "baby_clothing": "baby/baby-clothing-accessories",
    "baby_gear": "baby/baby-gear",
    "baby_feeding": "baby/baby-feeding",
    "baby_care": "baby/baby-care",
    "diapers": "baby/diapers-wipes",
    "baby_toys": "baby/baby-toys",
    
    # === TOYS ===
    "action_figures": "toys/action-figures-collectibles",
    "building_toys": "toys/building-toys",
    "dolls": "toys/dolls-accessories",
    "educational_toys": "toys/learning-education",
    "outdoor_toys": "toys/outdoor-play",
    "puzzles": "toys/puzzles",
    
    # === SPORTS & OUTDOORS ===
    "fitness_equipment": "sports-outdoors/sports-fitness/fitness-exercise",
    "sports_nutrition": "sports-outdoors/sports-fitness/sports-nutrition",
    "cycling": "sports-outdoors/outdoor-recreation/cycling",
    "camping": "sports-outdoors/outdoor-recreation/camping-hiking",
    "sports_accessories": "sports-outdoors/sports-fitness/sports-accessories",
    
    # === GROCERY ===
    "beverages": "grocery/beverages",
    "snacks": "grocery/snacks-sweets",
    "breakfast": "grocery/breakfast-cereal",
    "pantry": "grocery/pantry-staples",
    "frozen_food": "grocery/frozen-food",
    
    # === HEALTH & NUTRITION ===
    "vitamins": "health-nutrition/vitamins-supplements",
    "medical_supplies": "health-nutrition/medical-supplies-equipment",
    "personal_care": "health-nutrition/personal-care",
    
    # === BOOKS & MEDIA ===
    "books": "books-media/books",
    "ebooks": "books-media/ebooks",
    "magazines": "books-media/magazines",
    
    # === AUTOMOTIVE ===
    "car_accessories": "automotive/car-accessories",
    "car_electronics": "automotive/car-electronics-gps",
    "car_care": "automotive/car-care",
    
    # === OFFICE & STATIONERY ===
    "stationery": "stationery/office-supplies",
    "school_supplies": "stationery/school-supplies",
}

# Popular/High-value categories for focused scraping
HIGH_VALUE_CATEGORIES = {
    "smartphones": NOON_CATEGORIES["smartphones"],
    "laptops": NOON_CATEGORIES["laptops"],
    "tablets": NOON_CATEGORIES["tablets"],
    "smartwatches": NOON_CATEGORIES["smartwatches"],
    "headphones": NOON_CATEGORIES["headphones"],
    "cameras": NOON_CATEGORIES["cameras"],
    "tvs": NOON_CATEGORIES["tvs"],
    "gaming_consoles": NOON_CATEGORIES["gaming_consoles"],
}

# Fast-moving consumer goods
FMCG_CATEGORIES = {
    "grocery_beverages": NOON_CATEGORIES["beverages"],
    "grocery_snacks": NOON_CATEGORIES["snacks"],
    "baby_diapers": NOON_CATEGORIES["diapers"],
    "beauty_makeup": NOON_CATEGORIES["makeup"],
    "beauty_skincare": NOON_CATEGORIES["skincare"],
}