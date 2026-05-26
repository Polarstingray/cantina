

'''
inventory.py
    tracks how many of each food you currently have on hand
    stored separately from the catalog as a {name: quantity} map
'''

import os
import json
from grocery import read_json_from_bin, write_json_to_bin, FOOD_AND_MEALS, jsons_to_objects

INVENTORY = os.path.join(os.path.dirname(__file__), "inventory.bin")


# --- persistence -----------------------------------------------------------
# Inventory is a single json object {name: quantity}. Reuses the binary
# read/write helpers but defaults to {} (not []) since it's a map, not a list.

def read_inventory(db=INVENTORY) :
    data = read_json_from_bin(db)
    return data if data else {}        # read_json_from_bin returns [] when empty

def write_inventory(inv, db=INVENTORY) :
    write_json_to_bin(inv, db)


# --- queries ---------------------------------------------------------------
def get_quantity(name, db=INVENTORY) :
    return read_inventory(db).get(name, 0)

# True if at least `amount` of `name` is on hand. The cart uses this to decide
# whether a meal can be "afforded".
def has(name, amount=1, db=INVENTORY) :
    return get_quantity(name, db) >= amount


# --- mutations -------------------------------------------------------------
def add_stock(name, amount=1, db=INVENTORY) :
    if amount < 1 :
        return -1
    inv = read_inventory(db)
    inv[name] = inv.get(name, 0) + amount
    write_inventory(inv, db)
    return 0

# Rejects (returns -1) if there isn't enough on hand — does NOT clamp to 0.
# This is the key policy: you can't consume what you don't have.
def remove_stock(name, amount=1, db=INVENTORY) :
    if amount < 1 :
        return -1
    inv = read_inventory(db)
    if inv.get(name, 0) < amount :
        return -1
    inv[name] -= amount
    if inv[name] == 0 :
        inv.pop(name)
    write_inventory(inv, db)
    return 0

# Remove the entry entirely — call this when a food is deleted from the catalog
# so no orphan inventory survives (the referential-integrity cleanup we discussed).
def drop(name, db=INVENTORY) :
    inv = read_inventory(db)
    if inv.pop(name, None) is not None :
        write_inventory(inv, db)


# --- catalog-aware view ----------------------------------------------------
# Returns Food objects for everything on hand by hydrating names against the
# catalog. Skips (and could warn on) names with no catalog entry.

def on_hand_foods(catalog_db=FOOD_AND_MEALS, inv_db=INVENTORY) :
    foods, _ = jsons_to_objects(read_json_from_bin(catalog_db))
    by_name = {f.name : f for f in foods}
    inv = read_inventory(inv_db)
    return {by_name[name] : qty for name, qty in inv.items() if name in by_name}


def main() :
    add_stock("apple", 4)
    add_stock("pie crust")

main()