'''
api.py
    rough FastAPI scaffold exposing the catalog, inventory, and menu over HTTP
    so the LAN frontend can talk to the backend.

    setup:  pip install fastapi uvicorn
    run:    uvicorn api:app --reload --host 0.0.0.0 --port 8000
            (--host 0.0.0.0 makes it reachable from other devices on the LAN)
'''

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from foods import Food, Meal
from grocery import read_json_from_bin, FOOD_AND_MEALS, jsons_to_objects, add_to_bin
import inventory
import menu

app = FastAPI(title="Cantina")


# --- request bodies (rough) ------------------------------------------------

class FoodIn(BaseModel) :
    name: str
    stores: list[str] = []
    cost: float = 0.0
    cals: int = 0
    carbs: float = 0.0
    protein: float = 0.0
    fat: float = 0.0
    desc: str = ""

class MealIn(BaseModel) :
    name: str
    foods: dict[str, int]      # {food_name: amount}
    desc: str = ""

class StockIn(BaseModel) :
    name: str
    amount: int = 1
    kind: str = "food"         # "food" or "meal"


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
    _, meals = _catalog()
    return [m.to_json() for m in meals]

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

# TODO: DELETE /foods/{name} and /meals/{name} once catalog removal
# (the commented-out rm_from_db in grocery.py) is implemented. The handler
# should also call inventory.drop(name, kind) to clear orphaned stock.


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
