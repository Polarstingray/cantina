'''
inventory.py
    tracks how many of each food AND prepared meal you currently have on hand.
    stored separately from the catalog (grocery.py) as
        {"foods": {name: qty}, "meals": {name: qty}}
    food/meal details are not duplicated here -- they are looked up from the
    catalog by name when full objects are needed.

    NOTE: meals in inventory mean "prepared meals on hand" (e.g. leftovers),
    counted on their own. That is different from the menu's "what could I build"
    (see menu.py), which is computed from the food counts.
'''

import os
from grocery import read_json_from_bin, write_json_to_bin, FOOD_AND_MEALS, jsons_to_objects

INVENTORY = os.path.join(os.path.dirname(__file__), "inventory.bin")


# maps a catalog "type" ("food"/"meal") to its inventory section key
def _section(kind) :
    return "foods" if kind == "food" else "meals"


# --- persistence -----------------------------------------------------------
# Inventory is one json object with a "foods" and a "meals" section, each a
# {name: quantity} map. Reuses grocery.py's binary read/write helpers.

def read_inventory(db=INVENTORY) :
    data = read_json_from_bin(db)
    if not data :                       # read_json_from_bin returns [] when empty
        return {"foods" : {}, "meals" : {}}
    return data

def write_inventory(inv, db=INVENTORY) :
    write_json_to_bin(inv, db)


# --- queries ---------------------------------------------------------------

def get_quantity(name, kind="food", db=INVENTORY) :
    return read_inventory(db)[_section(kind)].get(name, 0)

# True if at least `amount` of `name` is on hand.
def has(name, amount=1, kind="food", db=INVENTORY) :
    return get_quantity(name, kind, db) >= amount


# --- mutations -------------------------------------------------------------

def add_stock(name, amount=1, kind="food", db=INVENTORY) :
    if amount <= 0 :
        return -1
    inv = read_inventory(db)
    section = inv[_section(kind)]
    section[name] = section.get(name, 0) + amount
    write_inventory(inv, db)
    return 0

# Rejects (returns -1, changing nothing) if there isn't enough on hand -- it
# does NOT clamp. You can't consume what you don't have; the cart relies on this.
# `amount` may be fractional; the zero-cleanup uses a small tolerance so we
# don't strand floating-point residue like 1.0 - 0.7 - 0.3 = -2.2e-16.
def remove_stock(name, amount=1, kind="food", db=INVENTORY) :
    if amount <= 0 :
        return -1
    inv = read_inventory(db)
    section = inv[_section(kind)]
    if section.get(name, 0) + 1e-9 < amount :
        return -1
    section[name] -= amount
    if section[name] <= 1e-9 :
        section.pop(name)               # keep the map free of zero-count entries
    write_inventory(inv, db)
    return 0

# Remove an entry entirely -- call when a food/meal is deleted from the catalog
# so no orphaned inventory survives (the referential-integrity cleanup).
def drop(name, kind="food", db=INVENTORY) :
    inv = read_inventory(db)
    if inv[_section(kind)].pop(name, None) is not None :
        write_inventory(inv, db)


# --- catalog-aware views ---------------------------------------------------
# Hydrate on-hand names into full objects by looking them up in the catalog.
# Names with no catalog entry are skipped.

def on_hand_foods(catalog_db=FOOD_AND_MEALS, inv_db=INVENTORY) :
    foods, _ = jsons_to_objects(read_json_from_bin(catalog_db))
    by_name = {f.name : f for f in foods}
    counts = read_inventory(inv_db)["foods"]
    return {by_name[name] : qty for name, qty in counts.items() if name in by_name}

def on_hand_meals(catalog_db=FOOD_AND_MEALS, inv_db=INVENTORY) :
    _, meals = jsons_to_objects(read_json_from_bin(catalog_db))
    by_name = {m.name : m for m in meals}
    counts = read_inventory(inv_db)["meals"]
    return {by_name[name] : qty for name, qty in counts.items() if name in by_name}


def main() :
    add_stock("apple", 4)
    add_stock("pie crust")
    add_stock("apple pie", 2, kind="meal")
    print(read_inventory())


if __name__ == "__main__" :
    main()
