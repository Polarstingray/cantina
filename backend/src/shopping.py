'''
shopping.py
    the household grocery (shopping) list. {name: amount} stored in
    shopping.bin alongside the other databases. Reuses grocery.py's
    locked + atomic + backed-up read/write helpers.

    auto-stub: adding a name not in the food catalog quietly creates a
    minimal Food(name) entry so the rest of the app has one name system.
'''

from grocery import (
    read_json_from_bin, write_json_to_bin, FOOD_AND_MEALS,
    jsons_to_objects, add_to_bin,
)
from foods import Food
from config import data_path
import inventory

SHOPPING = data_path("shopping.bin")


# --- persistence -----------------------------------------------------------

def read_list(db=SHOPPING) :
    data = read_json_from_bin(db)
    if not data :                       # read_json_from_bin returns [] when empty
        return {}
    return data

def write_list(list_, db=SHOPPING) :
    write_json_to_bin(list_, db)


# --- auto-stub -------------------------------------------------------------

# If `name` isn't a food in the catalog, drop a minimal Food(name) into it.
# Shared by /list/add and /inventory/add so non-catalog names converge on a
# single catalog entry rather than living as orphaned free text.
def ensure_in_catalog(name) :
    foods, _ = jsons_to_objects(read_json_from_bin(FOOD_AND_MEALS))
    if any(f.name == name for f in foods) :
        return
    add_to_bin(Food(name).to_json())


# --- mutations -------------------------------------------------------------

def add(name, amount=1, db=SHOPPING) :
    if amount <= 0 :
        return -1
    ensure_in_catalog(name)
    lst = read_list(db)
    lst[name] = lst.get(name, 0) + amount
    write_list(lst, db)
    return 0

def remove(name, amount=1, db=SHOPPING) :
    if amount <= 0 :
        return -1
    lst = read_list(db)
    if lst.get(name, 0) + 1e-9 < amount :
        return -1
    lst[name] -= amount
    if lst[name] <= 1e-9 :
        lst.pop(name)
    write_list(lst, db)
    return 0

# Check an item off the list. The full listed amount is removed; `to_inventory`
# (default = full listed amount, capped) is added to inventory as food. The
# remainder is silently discarded ("didn't end up buying it"). Returns the
# amount actually moved to inventory, or -1 if the item isn't on the list.
def check_off(name, to_inventory=None, db=SHOPPING) :
    lst = read_list(db)
    listed = lst.get(name, 0)
    if listed <= 0 :
        return -1
    moved = listed if to_inventory is None else max(0.0, min(float(to_inventory), listed))
    lst.pop(name)
    write_list(lst, db)
    if moved > 0 :
        inventory.add_stock(name, moved, "food")
    return moved

def clear(db=SHOPPING) :
    write_list({}, db)
