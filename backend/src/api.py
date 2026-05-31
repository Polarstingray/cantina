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

    @field_validator("name")
    @classmethod
    def _v_name(cls, v) : return _check_name(v)

class MealIn(BaseModel) :
    name: SafeName
    foods: dict[SafeName, Annotated[int, Field(ge=1)]]   # {food_name: amount}
    desc: Annotated[str, Field(max_length=500)] = ""

    @field_validator("name")
    @classmethod
    def _v_name(cls, v) : return _check_name(v)

class StockIn(BaseModel) :
    name: SafeName
    amount: Annotated[int, Field(ge=1)] = 1
    kind: Literal["food", "meal"] = "food"

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
             food.carbs, food.protein, food.fat, food.desc)
    add_to_bin(f.to_json())
    return {"ok" : True}

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


# --- static frontend -------------------------------------------------------
# Mount LAST so the API routes above still match first. html=True serves
# index.html at "/" and any unknown path falls back to it as well.
FRONTEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
