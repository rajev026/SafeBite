"""Thin client for the Open Food Facts API (free, no key needed)."""
import requests
from functools import lru_cache
from config import OFF_BASE, OFF_HEADERS

FIELDS = ("product_name,brands,quantity,ingredients_text,allergens_tags,traces_tags,"
          "nutriments,nutriscore_grade,nova_group,image_front_small_url")


@lru_cache(maxsize=256)
def fetch_product(barcode):
    """Look up one barcode. Returns a dict, or None if not found / network error."""
    try:
        r = requests.get(f"{OFF_BASE}/api/v2/product/{barcode}.json",
                         params={"fields": FIELDS}, headers=OFF_HEADERS, timeout=10)
        data = r.json()
    except (requests.RequestException, ValueError):
        return None
    if data.get("status") != 1:
        return None
    return data["product"]


@lru_cache(maxsize=256)
def search_by_name(name):
    """Best-effort lookup by dish/product name (used for menu items)."""
    try:
        r = requests.get(f"{OFF_BASE}/cgi/search.pl",
                         params={"search_terms": name, "search_simple": 1, "action": "process",
                                 "json": 1, "page_size": 1, "fields": FIELDS},
                         headers=OFF_HEADERS, timeout=10)
        products = r.json().get("products", [])
    except (requests.RequestException, ValueError):
        return None
    return products[0] if products else None


def nutrition_summary(product):
    """Pick the per-100g numbers we show in the UI."""
    n = (product or {}).get("nutriments") or {}
    rows = [("Energy", n.get("energy-kcal_100g"), "kcal"),
            ("Fat", n.get("fat_100g"), "g"),
            ("Saturated fat", n.get("saturated-fat_100g"), "g"),
            ("Carbohydrates", n.get("carbohydrates_100g"), "g"),
            ("Sugars", n.get("sugars_100g"), "g"),
            ("Fibre", n.get("fiber_100g"), "g"),
            ("Protein", n.get("proteins_100g"), "g"),
            ("Salt", n.get("salt_100g"), "g")]
    return [{"label": l, "value": round(v, 1), "unit": u} for l, v, u in rows if v is not None]
