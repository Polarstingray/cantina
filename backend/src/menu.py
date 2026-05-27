'''
menu.py
    computes what can be made from the food you have on hand.

    buildable_count(meal, food_counts) -> how many copies of a meal you can make
    menu(...)                          -> {meal_name: buildable count} for the catalog
    make_meal(meal, ...)               -> the "cart" action: consume a meal's
                                          ingredient foods from inventory
'''

from grocery import read_json_from_bin, FOOD_AND_MEALS, jsons_to_objects
from inventory import read_inventory, write_inventory, INVENTORY


# How many copies of `meal` can be built from the on-hand food counts.
# = min over ingredients of (on_hand // required); 0 if any ingredient is short.
# `food_counts` is the {name: qty} map from inventory's "foods" section.
def buildable_count(meal, food_counts) :
    if not meal.foods :
        return 0
    possible = []
    for food, required in meal.foods.items() :
        if required < 1 :
            continue
        possible.append(food_counts.get(food.name, 0) // required)
    return min(possible) if possible else 0


# {meal_name: how many can be made} for every meal in the catalog.
def menu(catalog_db=FOOD_AND_MEALS, inv_db=INVENTORY) :
    _, meals = jsons_to_objects(read_json_from_bin(catalog_db))
    food_counts = read_inventory(inv_db)["foods"]
    return {meal.name : buildable_count(meal, food_counts) for meal in meals}


# "Cart"/cooking action: spend a meal's ingredient foods from inventory, using
# food as currency. Returns -1 (changing nothing) if the meal isn't buildable.
# Does one read + one write rather than calling remove_stock per ingredient.
# NOTE: this only consumes foods. If you also want the finished meal tracked as
# on-hand, the caller can follow up with inventory.add_stock(meal.name, kind="meal").
def make_meal(meal, inv_db=INVENTORY) :
    inv = read_inventory(inv_db)
    food_counts = inv["foods"]
    if buildable_count(meal, food_counts) < 1 :
        return -1
    for food, required in meal.foods.items() :
        food_counts[food.name] -= required
        if food_counts[food.name] == 0 :
            food_counts.pop(food.name)
    write_inventory(inv, inv_db)
    return 0


def main() :
    print(menu())


if __name__ == "__main__" :
    main()
