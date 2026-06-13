'''
grocery.py
    The food + meal catalog. Storage moved from a flat JSON .bin file to SQLite
    (see db.py), but the interface is unchanged: read_json_from_bin returns the
    catalog as a list of {type:"food"/"meal", ...} dicts and write_json_to_bin
    persists such a list. add_to_bin / remove_from_bin / jsons_to_objects keep
    their old behavior on top of those two helpers, so api.py and the frontend
    are untouched by the move.

    Names are unique per household: re-adding an existing name replaces the old
    entry, and meals reference their ingredients by name.
'''

import json
from foods import *
from config import data_path
from db import get_conn, current_household_id, insert_food, insert_meal

# Catalog "token": still passed around by callers (api.py, menu.py) as the db
# handle. Storage is SQLite now, so the value is only an identifier.
FOOD_AND_MEALS = data_path("data.bin")


# --- catalog persistence (SQLite-backed) -----------------------------------
# read_json_from_bin / write_json_to_bin keep the old list-of-dicts contract so
# the rest of the app doesn't change. The `db` argument is vestigial (the
# catalog lives in one place now) and kept only for signature compatibility.

def read_json_from_bin(db=FOOD_AND_MEALS) :
    with get_conn() as conn :
        rows = conn.execute(
            '''SELECT name, stores, cost, cals, carbs, protein, fat, descr, pic,
                      brand, serving_size, barcode, fiber, sugar, sodium, category
               FROM foods WHERE household_id = ? ORDER BY id''',
            (current_household_id(),)).fetchall()
        catalog = []
        for r in rows :
            # Rebuild a Food and re-serialize so the dict shape matches exactly
            # what the API has always returned (numbers stringified, etc.).
            food = Food(r["name"], json.loads(r["stores"]), r["cost"], r["cals"],
                        r["carbs"], r["protein"], r["fat"], r["descr"], r["pic"],
                        brand=r["brand"], serving_size=r["serving_size"],
                        barcode=r["barcode"], fiber=r["fiber"], sugar=r["sugar"],
                        sodium=r["sodium"], category=r["category"])
            catalog.append(food.to_json())

        meals = conn.execute(
            "SELECT id, name, descr, pic, category FROM meals WHERE household_id = ? ORDER BY id",
            (current_household_id(),)).fetchall()
        for m in meals :
            ing = conn.execute(
                "SELECT food_name, amount FROM meal_ingredients WHERE meal_id = ? ORDER BY rowid",
                (m["id"],)).fetchall()
            catalog.append({
                "type": "meal",
                "name": m["name"],
                "foods": {i["food_name"]: i["amount"] for i in ing},
                "desc": m["descr"],
                "pic": m["pic"],
                "category": m["category"],
            })
        return catalog


def write_json_to_bin(json_list, db=FOOD_AND_MEALS) :
    '''Replace the whole catalog with `json_list` (a list of food/meal dicts).'''
    hid = current_household_id()
    with get_conn() as conn :
        conn.execute(
            "DELETE FROM meal_ingredients WHERE meal_id IN "
            "(SELECT id FROM meals WHERE household_id = ?)", (hid,))
        conn.execute("DELETE FROM meals WHERE household_id = ?", (hid,))
        conn.execute("DELETE FROM foods WHERE household_id = ?", (hid,))
        for obj in json_list :
            if obj.get("type") == "food" :
                food = Food.create(obj)
                if food :
                    insert_food(conn, food, hid)
            elif obj.get("type") == "meal" and obj.get("name") :
                insert_meal(conn, obj.get("name"), obj.get("desc") or "",
                            obj.get("pic"), obj.get("foods") or {}, hid,
                            category=obj.get("category") or "")


# Rebuild Food and Meal objects from the json list. Foods are built first so
# that each meal can resolve its ingredient names against the food catalog.
# Returns [food_list, meal_list].
def jsons_to_objects(json_list) :
    foods = []
    meal_jsons = []
    for obj in json_list :
        if obj.get("type") == "food" :
            food = Food.create(obj)
            if food :
                foods.append(food)
        elif obj.get("type") == "meal" :
            meal_jsons.append(obj)

    food_catalog = {food.name : food for food in foods}

    meals = []
    for obj in meal_jsons :
        meal = Meal.create(obj, food_catalog)
        if meal :
            meals.append(meal)
    return [foods, meals]


# Enforce the unique-name rule and serialize the food/meal objects back into a
# json list. data is [food_list, meal_list].
def objects_to_jsons(data) :
    foods, meals = data
    json_list = []
    for food in unique_list(foods, []) :
        json_list.append(food.to_json())
    for meal in unique_list(meals, []) :
        json_list.append(meal.to_json())
    return json_list

def unique_list(dat1, dat2) :
    combined = list(dat1) + list(dat2)

    # For a duplicate name the most-recently-added entry wins, but the
    # surviving entries keep their original insertion order (the slot where
    # the name first appeared). This avoids reversing the list on every call.
    latest = {}
    for obj in combined :
        latest[obj.name] = obj

    names = []
    unique_objects = []
    for obj in combined :
        if obj.name not in names :
            names.append(obj.name)
            unique_objects.append(latest[obj.name])
    return unique_objects

def add_to_bin(item, db=FOOD_AND_MEALS) :
    old_db = read_json_from_bin(db)
    old_db.append(item)
    new_db = objects_to_jsons(jsons_to_objects(old_db)) # ensures no duplicates
    write_json_to_bin(new_db, db)
    return


# Remove a food or meal from the catalog by name. `kind` is "food" or "meal".
# Returns 0 on success, -1 if no matching entry was found. Inventory cleanup
# (dropping orphaned on-hand rows) is the caller's responsibility -- the API
# layer pairs this with inventory.drop(name, kind).
def remove_from_bin(name, kind="food", db=FOOD_AND_MEALS) :
    data = read_json_from_bin(db)
    new_data = [obj for obj in data
                if not (obj.get("type") == kind and obj.get("name") == name)]
    if len(new_data) == len(data) :
        return -1
    write_json_to_bin(new_data, db)
    return 0
