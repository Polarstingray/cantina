'''
lookup.py
    Barcode -> food data via OpenFoodFacts. Returns a dict shaped like
    FoodIn (so the frontend can prefill the add-food form) -- not a raw
    OpenFoodFacts payload. No new dependency: stdlib urllib only.

    A small in-process cache (bounded ~100 entries) avoids hitting the
    network repeatedly during a single shopping trip.
'''

import json
import urllib.request
import urllib.error

OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
TIMEOUT_SECONDS = 5
USER_AGENT = "cantina/1.0 (https://github.com/local-household)"

_CACHE: dict[str, dict] = {}
_CACHE_LIMIT = 100


# Pick the best available numeric for a given nutriment field. OpenFoodFacts
# exposes both `_serving` (per labeled serving) and `_100g` (per 100g). We
# prefer per-serving since the rest of the app stores per-serving values.
def _pick_num(nutriments: dict, key: str) -> float :
    for suffix in ("_serving", "_100g", "") :
        v = nutriments.get(key + suffix)
        if v is None :
            continue
        try :
            return float(v)
        except (TypeError, ValueError) :
            continue
    return 0.0


def _map_off_to_food(payload: dict) -> dict | None :
    if payload.get("status") != 1 :
        return None
    p = payload.get("product") or {}
    nutriments = p.get("nutriments") or {}

    name = (p.get("product_name") or p.get("product_name_en") or "").strip()
    if not name :
        # OpenFoodFacts sometimes returns 200 with status=1 but no name.
        return None

    return {
        "name": name[:80],
        "brand": (p.get("brands") or "").strip()[:80],
        "serving_size": (p.get("serving_size") or "").strip()[:80],
        "barcode": (p.get("code") or "").strip(),
        "cals": int(round(_pick_num(nutriments, "energy-kcal"))),
        "carbs": _pick_num(nutriments, "carbohydrates"),
        "protein": _pick_num(nutriments, "proteins"),
        "fat": _pick_num(nutriments, "fat"),
        "fiber": _pick_num(nutriments, "fiber"),
        "sugar": _pick_num(nutriments, "sugars"),
        # OpenFoodFacts returns sodium in grams; convert to mg.
        "sodium": _pick_num(nutriments, "sodium") * 1000.0,
        # cost + stores stay empty -- user supplies those locally.
        "cost": 0.0,
        "stores": [],
        "desc": "",
    }


def lookup(code: str) -> dict | None :
    code = (code or "").strip()
    if not code or not code.isdigit() :
        return None
    if code in _CACHE :
        return _CACHE[code]

    req = urllib.request.Request(OFF_URL.format(code=code),
                                 headers={"User-Agent": USER_AGENT})
    try :
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp :
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) :
        return None

    food = _map_off_to_food(data)
    if food is not None :
        if len(_CACHE) >= _CACHE_LIMIT :
            # cheap eviction: drop the oldest insertion (dicts are insertion-ordered)
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[code] = food
    return food
