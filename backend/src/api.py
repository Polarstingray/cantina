'''
api.py
    rough FastAPI scaffold exposing the catalog, inventory, and menu over HTTP
    so the LAN frontend can talk to the backend.

    setup:  pip install -r ../requirements.txt
    run:    python api.py                       (honors CANTINA_HOST / CANTINA_PORT)
        or  uvicorn api:app --host 0.0.0.0 --port 8000
            (--host 0.0.0.0 makes it reachable from other devices on the LAN)
'''

import logging
import os
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

import config
import auth
import ratelimit
from foods import Food, Meal
from grocery import read_json_from_bin, FOOD_AND_MEALS, jsons_to_objects, add_to_bin, remove_from_bin
import inventory
import menu
import shopping
import lookup
import spending

log = logging.getLogger("cantina.auth")

# Swagger/OpenAPI reveal the whole API surface, so they're off unless explicitly
# enabled for local development.
_ENABLE_DOCS = os.environ.get("CANTINA_ENABLE_DOCS", "0") == "1"
app = FastAPI(title="Cantina",
              docs_url="/docs" if _ENABLE_DOCS else None,
              redoc_url="/redoc" if _ENABLE_DOCS else None,
              openapi_url="/openapi.json" if _ENABLE_DOCS else None)

# Every data route requires a logged-in user. The dependency also scopes the
# request to that user's household (see auth.get_current_user), so the handlers
# below need no auth/household code of their own. Auth + static routes stay on
# `app` so login itself isn't gated.
router = APIRouter(dependencies=[Depends(auth.get_current_user)])


# --- security middleware ---------------------------------------------------

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        # script-src adds 'wasm-unsafe-eval' so the vendored ZXing barcode
        # decoder can compile its WebAssembly (camera scanning on iOS/Firefox,
        # which lack the native BarcodeDetector). That token permits WASM
        # compilation only -- NOT JS eval. The .wasm itself is same-origin, so
        # default-src 'self' still covers fetching it.
        "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; "
        "img-src 'self' data:; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_HEADER = "x-requested-with"
_CSRF_VALUE = "cantina"


@app.middleware("http")
async def security_middleware(request: Request, call_next) :
    # CSRF: state-changing requests must carry our custom header. A cross-site
    # page can't set it without a CORS grant (we allow none), and SameSite=Strict
    # already keeps the session cookie off cross-site requests -- defense in depth.
    if request.method not in _SAFE_METHODS :
        if request.headers.get(_CSRF_HEADER, "").lower() != _CSRF_VALUE :
            return JSONResponse({"detail": "missing or invalid X-Requested-With header"}, status_code=403)
    response = await call_next(request)
    for key, value in _SECURITY_HEADERS.items() :
        response.headers.setdefault(key, value)
    if auth.SECURE_COOKIES :     # only meaningful (and safe) once served over HTTPS
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    # Cache policy (Cloudflare is set to respect these origin headers):
    #   - vendored decoder is version-pinned, effectively immutable -> cache hard
    #   - API JSON is per-household + auth-gated -> never store it
    #   - the SPA shell (html/js/css) -> revalidate via etag, so a deploy is
    #     visible on the next load instead of sitting behind a 4h stale copy
    path = request.url.path
    if path.startswith("/js/vendor/") :
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif response.headers.get("content-type", "").startswith("application/json") :
        response.headers.setdefault("Cache-Control", "no-store")
    else :
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


# --- request bodies --------------------------------------------------------

# Names: 1..80 chars, stripped, no path separators or null bytes.
SafeName = Annotated[str, Field(min_length=1, max_length=80, strip_whitespace=True)]

def _check_name(value: str) -> str :
    if "/" in value or "\\" in value or "\x00" in value :
        raise ValueError("name may not contain '/', '\\\\' or null bytes")
    return value


class FoodIn(BaseModel) :
    name: SafeName
    stores: list[Annotated[str, Field(max_length=80)]] = []
    cost: float = Field(0.0, ge=0)
    cals: int = Field(0, ge=0)
    carbs: float = Field(0.0, ge=0)
    protein: float = Field(0.0, ge=0)
    fat: float = Field(0.0, ge=0)
    desc: Annotated[str, Field(max_length=500)] = ""
    # Optional metadata (from barcode lookup or manual entry).
    brand: Annotated[str, Field(max_length=80)] = ""
    serving_size: Annotated[str, Field(max_length=80)] = ""
    barcode: Annotated[str, Field(max_length=32)] = ""
    fiber: float = Field(0.0, ge=0)
    sugar: float = Field(0.0, ge=0)
    sodium: float = Field(0.0, ge=0)            # in mg
    category: Annotated[str, Field(max_length=40)] = ""

    @field_validator("name")
    @classmethod
    def _v_name(cls, v) : return _check_name(v)

class MealIn(BaseModel) :
    name: SafeName
    foods: dict[SafeName, Annotated[float, Field(gt=0)]]   # {food_name: amount}
    desc: Annotated[str, Field(max_length=500)] = ""
    category: Annotated[str, Field(max_length=40)] = ""

    @field_validator("name")
    @classmethod
    def _v_name(cls, v) : return _check_name(v)

class StockIn(BaseModel) :
    name: SafeName
    amount: Annotated[float, Field(gt=0)] = 1.0
    kind: Literal["food", "meal"] = "food"

    @field_validator("name")
    @classmethod
    def _v_name(cls, v) : return _check_name(v)

class ListItemIn(BaseModel) :
    name: SafeName
    amount: Annotated[float, Field(gt=0)] = 1.0

    @field_validator("name")
    @classmethod
    def _v_name(cls, v) : return _check_name(v)

class CheckOffIn(BaseModel) :
    name: SafeName
    to_inventory: Annotated[float, Field(ge=0)] | None = None

    @field_validator("name")
    @classmethod
    def _v_name(cls, v) : return _check_name(v)

class PurchaseIn(BaseModel) :
    name: SafeName
    qty: Annotated[float, Field(gt=0)] = 1.0
    unit_cost: Annotated[float, Field(ge=0)] = 0.0
    source: Literal["checkoff", "stock", "manual"] = "manual"

    @field_validator("name")
    @classmethod
    def _v_name(cls, v) : return _check_name(v)


# small helper: load the catalog as ([Food], [Meal])
def _catalog() :
    return jsons_to_objects(read_json_from_bin(FOOD_AND_MEALS))


# --- catalog ---------------------------------------------------------------

@router.get("/foods")
def list_foods() :
    foods, _ = _catalog()
    return [f.to_json() for f in foods]

@router.get("/meals")
def list_meals() :
    # Return raw catalog rows (not rebuilt Meal objects) so the frontend can
    # see ingredient names that no longer exist in the food catalog and warn
    # the user, rather than silently dropping them like Meal.create does.
    return [obj for obj in read_json_from_bin(FOOD_AND_MEALS)
            if obj.get("type") == "meal"]

@router.post("/foods")
def add_food(food: FoodIn) :
    f = Food(food.name, food.stores, food.cost, food.cals,
             food.carbs, food.protein, food.fat, food.desc,
             brand=food.brand, serving_size=food.serving_size, barcode=food.barcode,
             fiber=food.fiber, sugar=food.sugar, sodium=food.sodium, category=food.category)
    add_to_bin(f.to_json())
    return {"ok" : True}

# PUT is semantically "replace this named food" -- add_to_bin already
# deduplicates by name, so the implementation is the same as POST. Kept
# separate so the UI can express edit-vs-create intent.
@router.put("/foods/{name}")
def update_food(name: str, food: FoodIn) :
    if name != food.name :
        raise HTTPException(status_code=400, detail="path name and body name must match")
    f = Food(food.name, food.stores, food.cost, food.cals,
             food.carbs, food.protein, food.fat, food.desc,
             brand=food.brand, serving_size=food.serving_size, barcode=food.barcode,
             fiber=food.fiber, sugar=food.sugar, sodium=food.sodium, category=food.category)
    add_to_bin(f.to_json())
    return {"ok" : True}

# Proxy + transform: barcode -> FoodIn-shaped dict (or 404). The frontend
# uses this to prefill the add-food form; saving the food is a separate POST/PUT.
@router.get("/lookup/barcode/{code}")
def lookup_barcode(code: str) :
    if not code.isdigit() or len(code) > 32 :
        raise HTTPException(status_code=400, detail="barcode must be digits, <=32 chars")
    result = lookup.lookup(code)
    if result is None :
        raise HTTPException(status_code=404, detail=f"no product found for barcode '{code}'")
    return result

@router.get("/catalog/uses/{food_name}")
def food_uses(food_name: str) :
    # Meals (by name) that reference this food in their ingredient map.
    return [obj["name"] for obj in read_json_from_bin(FOOD_AND_MEALS)
            if obj.get("type") == "meal" and food_name in (obj.get("foods") or {})]

@router.post("/meals")
def add_meal(meal: MealIn) :
    foods_by_name = {f.name : f for f in _catalog()[0]}
    ingredients = {}
    for name, amount in meal.foods.items() :
        if name not in foods_by_name :
            raise HTTPException(status_code=400, detail=f"unknown food '{name}'")
        ingredients[foods_by_name[name]] = amount
    m = Meal(meal.name, ingredients, desc=meal.desc, category=meal.category)
    add_to_bin(m.to_json())
    return {"ok" : True}

@router.delete("/foods/{name}")
def delete_food(name: str) :
    if remove_from_bin(name, kind="food") != 0 :
        raise HTTPException(status_code=404, detail=f"unknown food '{name}'")
    inventory.drop(name, kind="food")
    return {"ok" : True}

@router.delete("/meals/{name}")
def delete_meal(name: str) :
    if remove_from_bin(name, kind="meal") != 0 :
        raise HTTPException(status_code=404, detail=f"unknown meal '{name}'")
    inventory.drop(name, kind="meal")
    return {"ok" : True}


# --- inventory -------------------------------------------------------------

@router.get("/inventory")
def get_inventory() :
    return inventory.read_inventory()

@router.post("/inventory/add")
def add_stock(stock: StockIn) :
    # Stocking an unknown food creates a minimal catalog entry so the rest of
    # the app sees one name system (matches the grocery-list add behavior).
    if stock.kind == "food" :
        shopping.ensure_in_catalog(stock.name)
    if inventory.add_stock(stock.name, stock.amount, stock.kind) != 0 :
        raise HTTPException(status_code=400, detail="invalid amount")
    return {"ok" : True}

@router.post("/inventory/remove")
def remove_stock(stock: StockIn) :
    if inventory.remove_stock(stock.name, stock.amount, stock.kind) != 0 :
        raise HTTPException(status_code=400, detail="not enough on hand")
    return {"ok" : True}


# --- menu ------------------------------------------------------------------

@router.get("/menu")
def get_menu() :
    return menu.menu()

# Spend a meal's ingredients from inventory (the "cart" action).
@router.post("/menu/make/{meal_name}")
def make_meal(meal_name: str) :
    _, meals = _catalog()
    target = next((m for m in meals if m.name == meal_name), None)
    if target is None :
        raise HTTPException(status_code=404, detail=f"unknown meal '{meal_name}'")
    if menu.make_meal(target) != 0 :
        raise HTTPException(status_code=400, detail="not enough ingredients on hand")
    return {"ok" : True}


# --- grocery / shopping list ----------------------------------------------

@router.get("/list")
def get_list() :
    return shopping.read_list()

@router.post("/list/add")
def list_add(item: ListItemIn) :
    if shopping.add(item.name, item.amount) != 0 :
        raise HTTPException(status_code=400, detail="invalid amount")
    return {"ok" : True}

@router.post("/list/remove")
def list_remove(item: ListItemIn) :
    if shopping.remove(item.name, item.amount) != 0 :
        raise HTTPException(status_code=400, detail="not enough on the list")
    return {"ok" : True}

@router.post("/list/check")
def list_check(body: CheckOffIn) :
    moved = shopping.check_off(body.name, body.to_inventory)
    if moved < 0 :
        raise HTTPException(status_code=404, detail=f"'{body.name}' not on the list")
    return {"moved" : moved}

@router.post("/list/clear")
def list_clear() :
    shopping.clear()
    return {"ok" : True}


# --- spending log ----------------------------------------------------------

@router.get("/spending")
def get_spending(since: str | None = None, until: str | None = None) :
    return spending.read_entries(since=since, until=until)

@router.get("/spending/totals")
def get_spending_totals(bucket: Literal["week", "month"] = "week") :
    return spending.totals_by_week() if bucket == "week" else spending.totals_by_month()

@router.post("/spending")
def post_spending(body: PurchaseIn) :
    entry = spending.add_entry(body.name, body.qty, body.unit_cost, body.source)
    if entry is None :
        raise HTTPException(status_code=400, detail="qty must be > 0, unit_cost >= 0")
    return entry

@router.delete("/spending/{entry_id}")
def delete_spending(entry_id: int) :
    if spending.delete_entry(entry_id) != 0 :
        raise HTTPException(status_code=404, detail=f"no spending entry id={entry_id}")
    return {"ok" : True}

# Sugar endpoints so the frontend doesn't have to remember which "source"
# string to send when logging a purchase that came from one of the flows.
@router.post("/spending/from-checkoff")
def post_spending_from_checkoff(body: PurchaseIn) :
    body.source = "checkoff"
    return post_spending(body)

@router.post("/spending/from-stock-add")
def post_spending_from_stock_add(body: PurchaseIn) :
    body.source = "stock"
    return post_spending(body)


# --- auth -------------------------------------------------------------------
# These stay on `app` (not the gated router): login/logout must work without a
# session, and /auth/me, /auth/users carry their own dependency.

class LoginIn(BaseModel) :
    email: Annotated[str, Field(max_length=254)]
    password: Annotated[str, Field(min_length=1, max_length=200)]

class NewUserIn(BaseModel) :
    email: Annotated[str, Field(max_length=254)]
    password: Annotated[str, Field(min_length=auth.MIN_PASSWORD_LENGTH, max_length=200)]
    role: Literal["admin", "member"] = "member"


@app.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response) :
    ip = ratelimit.client_ip(request)
    email = body.email.strip().lower()
    wait = ratelimit.retry_after(ip, email)
    if wait is not None :
        log.warning("login throttled ip=%s email=%s", ip, email)
        raise HTTPException(status_code=429, detail="too many attempts, please wait and try again",
                            headers={"Retry-After": str(wait)})
    user = auth.authenticate(body.email, body.password)
    if not user :
        ratelimit.record_failure(ip, email)
        log.warning("login failed ip=%s email=%s", ip, email)
        raise HTTPException(status_code=401, detail="invalid email or password")
    ratelimit.clear(ip, email)
    auth.set_session_cookie(response, auth.create_session(user["id"]))
    log.info("login ok ip=%s email=%s", ip, user["email"])
    return {"ok": True, "user": {"email": user["email"], "role": user["role"]}}

@app.post("/auth/logout")
def logout(request: Request, response: Response) :
    auth.delete_session(request.cookies.get(auth.COOKIE_NAME))
    auth.clear_session_cookie(response)
    return {"ok": True}

@app.post("/auth/logout-all")
async def logout_all(response: Response, user=Depends(auth.get_current_user)) :
    # Revoke every session for this user (e.g. after a suspected compromise).
    auth.delete_user_sessions(user["id"])
    auth.clear_session_cookie(response)
    return {"ok": True}

@app.get("/auth/me")
async def whoami(user=Depends(auth.get_current_user)) :
    return {"email": user["email"], "role": user["role"], "household_id": user["household_id"]}

@app.get("/auth/users")
async def get_users(admin=Depends(auth.require_admin)) :
    return auth.list_users(admin["household_id"])

@app.post("/auth/users")
async def post_user(body: NewUserIn, admin=Depends(auth.require_admin)) :
    # New members join the admin's household.
    try :
        uid = auth.create_user(body.email, body.password, body.role, admin["household_id"])
    except ValueError as e :
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "id": uid}


# --- static frontend -------------------------------------------------------
# Register the gated data routes, then mount the static frontend LAST so the
# API routes above still match first. html=True serves index.html at "/" and
# any unknown path falls back to it as well.
app.include_router(router)

FRONTEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


# Run the server honoring CANTINA_HOST / CANTINA_PORT (see config.py). Lets a
# deploy override host/port via the environment instead of CLI flags.
if __name__ == "__main__" :
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
