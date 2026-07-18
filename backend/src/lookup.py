'''
lookup.py
    Barcode -> food data via OpenFoodFacts, plus a best-effort price
    lookup against the sibling Open Prices project. Returns a dict
    shaped like FoodIn (so the frontend can prefill the add-food form)
    -- not raw payloads. Stdlib urllib only, no new dependency.

    A small in-process cache (bounded ~100 entries) avoids hitting the
    network repeatedly during a single shopping trip. The cached entry
    holds the merged result (food + price).
'''

import json
import urllib.request
import urllib.error

OFF_URL    = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
PRICES_URL = ("https://prices.openfoodfacts.org/api/v1/prices"
              "?product_code={code}&currency=USD&order_by=-date&size=5")
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
        # Round macros to 1 decimal so the prefilled values satisfy the add-food
        # form's step="0.1" inputs -- OpenFoodFacts often returns finer precision
        # (e.g. fat 1.205), which HTML5 validation would otherwise reject on save.
        "cals": int(round(_pick_num(nutriments, "energy-kcal"))),
        "carbs": round(_pick_num(nutriments, "carbohydrates"), 1),
        "protein": round(_pick_num(nutriments, "proteins"), 1),
        "fat": round(_pick_num(nutriments, "fat"), 1),
        "fiber": round(_pick_num(nutriments, "fiber"), 1),
        "sugar": round(_pick_num(nutriments, "sugars"), 1),
        # OpenFoodFacts returns sodium in grams; convert to mg.
        "sodium": round(_pick_num(nutriments, "sodium") * 1000.0, 1),
        # cost + stores stay empty -- user supplies those locally.
        "cost": 0.0,
        "stores": [],
        "desc": "",
    }


# Best-effort USD price lookup from Open Prices. Returns the most recent
# observation's price (float USD) or None on any failure / no observations.
# Open Prices coverage is sparse, especially for US products -- callers
# should treat None as "no data", not as an error.
def _fetch_prices(code: str) -> float | None :
    req = urllib.request.Request(PRICES_URL.format(code=code),
                                 headers={"User-Agent": USER_AGENT})
    try :
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp :
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) :
        return None
    items = data.get("items") or []
    for obs in items :                # already sorted newest first by -date
        price = obs.get("price")
        try :
            p = float(price)
            if p > 0 :
                return p
        except (TypeError, ValueError) :
            continue
    return None


def lookup(code: str) -> dict | None :
    code = (code or "").strip()
    # ASCII digits only -- bare isdigit() also accepts Unicode digits, which
    # would end up interpolated into the outbound request URL.
    if not code or not (code.isascii() and code.isdigit()) :
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
    if food is None :
        return None

    # Best-effort price overlay; silent miss leaves cost=0.0. Round to cents to
    # match the cost field's step="0.01".
    price = _fetch_prices(code)
    if price is not None :
        food["cost"] = round(price, 2)

    if len(_CACHE) >= _CACHE_LIMIT :
        # cheap eviction: drop the oldest insertion (dicts are insertion-ordered)
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[code] = food
    return food
