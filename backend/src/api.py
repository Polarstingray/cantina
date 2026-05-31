'''
api.py
    rough FastAPI scaffold exposing the catalog, inventory, and menu over HTTP
    so the LAN frontend can talk to the backend.

    setup:  pip install fastapi uvicorn
    run:    uvicorn api:app --reload --host 0.0.0.0 --port 8000
            (--host 0.0.0.0 makes it reachable from other devices on the LAN)
'''

import os
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from foods import Food, Meal
from grocery import read_json_from_bin, FOOD_AND_MEALS, jsons_to_objects, add_to_bin, remove_from_bin
import inventory
import menu
import shopping
import lookup
import spending

app = FastAPI(title="Cantina")


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

    @field_validator("name")
    @classmethod
    def _v_name(cls, v) : return _check_name(v)

class MealIn(BaseModel) :
    name: SafeName
    foods: dict[SafeName, Annotated[float, Field(gt=0)]]   # {food_name: amount}
    desc: Annotated[str, Field(max_length=500)] = ""

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

@app.get("/foods")
def list_foods() :
    foods, _ = _catalog()
    return [f.to_json() for f in foods]

@app.get("/meals")
def list_meals() :
    # Return raw catalog rows (not rebuilt Meal objects) so the frontend can
    # see ingredient names that no longer exist in the food catalog and warn
    # the user, rather than silently dropping them like Meal.create does.
    return [obj for obj in read_json_from_bin(FOOD_AND_MEALS)
            if obj.get("type") == "meal"]

@app.post("/foods")
def add_food(food: FoodIn) :
    f = Food(food.name, food.stores, food.cost, food.cals,
             food.carbs, food.protein, food.fat, food.desc,
             brand=food.brand, serving_size=food.serving_size, barcode=food.barcode,
             fiber=food.fiber, sugar=food.sugar, sodium=food.sodium)
    add_to_bin(f.to_json())
    return {"ok" : True}

# PUT is semantically "replace this named food" -- add_to_bin already
# deduplicates by name, so the implementation is the same as POST. Kept
# separate so the UI can express edit-vs-create intent.
@app.put("/foods/{name}")
def update_food(name: str, food: FoodIn) :
    if name != food.name :
        raise HTTPException(status_code=400, detail="path name and body name must match")
    f = Food(food.name, food.stores, food.cost, food.cals,
             food.carbs, food.protein, food.fat, food.desc,
             brand=food.brand, serving_size=food.serving_size, barcode=food.barcode,
             fiber=food.fiber, sugar=food.sugar, sodium=food.sodium)
    add_to_bin(f.to_json())
    return {"ok" : True}

# Proxy + transform: barcode -> FoodIn-shaped dict (or 404). The frontend
# uses this to prefill the add-food form; saving the food is a separate POST/PUT.
@app.get("/lookup/barcode/{code}")
def lookup_barcode(code: str) :
    if not code.isdigit() or len(code) > 32 :
        raise HTTPException(status_code=400, detail="barcode must be digits, <=32 chars")
    result = lookup.lookup(code)
    if result is None :
        raise HTTPException(status_code=404, detail=f"no product found for barcode '{code}'")
    return result

@app.get("/catalog/uses/{food_name}")
def food_uses(food_name: str) :
    # Meals (by name) that reference this food in their ingredient map.
    return [obj["name"] for obj in read_json_from_bin(FOOD_AND_MEALS)
            if obj.get("type") == "meal" and food_name in (obj.get("foods") or {})]

@app.post("/meals")
def add_meal(meal: MealIn) :
    foods_by_name = {f.name : f for f in _catalog()[0]}
    ingredients = {}
    for name, amount in meal.foods.items() :
        if name not in foods_by_name :
            raise HTTPException(status_code=400, detail=f"unknown food '{name}'")
        ingredients[foods_by_name[name]] = amount
    m = Meal(meal.name, ingredients, desc=meal.desc)
    add_to_bin(m.to_json())
    return {"ok" : True}

@app.delete("/foods/{name}")
def delete_food(name: str) :
    if remove_from_bin(name, kind="food") != 0 :
        raise HTTPException(status_code=404, detail=f"unknown food '{name}'")
    inventory.drop(name, kind="food")
    return {"ok" : True}

@app.delete("/meals/{name}")
def delete_meal(name: str) :
    if remove_from_bin(name, kind="meal") != 0 :
        raise HTTPException(status_code=404, detail=f"unknown meal '{name}'")
    inventory.drop(name, kind="meal")
    return {"ok" : True}


# --- inventory -------------------------------------------------------------

@app.get("/inventory")
def get_inventory() :
    return inventory.read_inventory()

@app.post("/inventory/add")
def add_stock(stock: StockIn) :
    # Stocking an unknown food creates a minimal catalog entry so the rest of
    # the app sees one name system (matches the grocery-list add behavior).
    if stock.kind == "food" :
        shopping.ensure_in_catalog(stock.name)
    if inventory.add_stock(stock.name, stock.amount, stock.kind) != 0 :
        raise HTTPException(status_code=400, detail="invalid amount")
    return {"ok" : True}

@app.post("/inventory/remove")
def remove_stock(stock: StockIn) :
    if inventory.remove_stock(stock.name, stock.amount, stock.kind) != 0 :
        raise HTTPException(status_code=400, detail="not enough on hand")
    return {"ok" : True}


# --- menu ------------------------------------------------------------------

@app.get("/menu")
def get_menu() :
    return menu.menu()

# Spend a meal's ingredients from inventory (the "cart" action).
@app.post("/menu/make/{meal_name}")
def make_meal(meal_name: str) :
    _, meals = _catalog()
    target = next((m for m in meals if m.name == meal_name), None)
    if target is None :
        raise HTTPException(status_code=404, detail=f"unknown meal '{meal_name}'")
    if menu.make_meal(target) != 0 :
        raise HTTPException(status_code=400, detail="not enough ingredients on hand")
    return {"ok" : True}


# --- grocery / shopping list ----------------------------------------------

@app.get("/list")
def get_list() :
    return shopping.read_list()

@app.post("/list/add")
def list_add(item: ListItemIn) :
    if shopping.add(item.name, item.amount) != 0 :
        raise HTTPException(status_code=400, detail="invalid amount")
    return {"ok" : True}

@app.post("/list/remove")
def list_remove(item: ListItemIn) :
    if shopping.remove(item.name, item.amount) != 0 :
        raise HTTPException(status_code=400, detail="not enough on the list")
    return {"ok" : True}

@app.post("/list/check")
def list_check(body: CheckOffIn) :
    moved = shopping.check_off(body.name, body.to_inventory)
    if moved < 0 :
        raise HTTPException(status_code=404, detail=f"'{body.name}' not on the list")
    return {"moved" : moved}

@app.post("/list/clear")
def list_clear() :
    shopping.clear()
    return {"ok" : True}


# --- spending log ----------------------------------------------------------

@app.get("/spending")
def get_spending(since: str | None = None, until: str | None = None) :
    return spending.read_entries(since=since, until=until)

@app.get("/spending/totals")
def get_spending_totals(bucket: Literal["week", "month"] = "week") :
    return spending.totals_by_week() if bucket == "week" else spending.totals_by_month()

@app.post("/spending")
def post_spending(body: PurchaseIn) :
    entry = spending.add_entry(body.name, body.qty, body.unit_cost, body.source)
    if entry is None :
        raise HTTPException(status_code=400, detail="qty must be > 0, unit_cost >= 0")
    return entry

@app.delete("/spending/{entry_id}")
def delete_spending(entry_id: int) :
    if spending.delete_entry(entry_id) != 0 :
        raise HTTPException(status_code=404, detail=f"no spending entry id={entry_id}")
    return {"ok" : True}

# Sugar endpoints so the frontend doesn't have to remember which "source"
# string to send when logging a purchase that came from one of the flows.
@app.post("/spending/from-checkoff")
def post_spending_from_checkoff(body: PurchaseIn) :
    body.source = "checkoff"
    return post_spending(body)

@app.post("/spending/from-stock-add")
def post_spending_from_stock_add(body: PurchaseIn) :
    body.source = "stock"
    return post_spending(body)


# --- static frontend -------------------------------------------------------
# Mount LAST so the API routes above still match first. html=True serves
# index.html at "/" and any unknown path falls back to it as well.
FRONTEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
