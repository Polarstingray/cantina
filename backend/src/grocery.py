'''
grocery.py
    write and read from binary database (sqlite in the future) and dynamic grocery list csv
    add food items to database
    add meals to database
    keep track of a list of foods, their cost, and where to buy them
'''

import os
import json
from foods import *
FOOD_AND_MEALS=os.path.join(os.path.dirname(__file__), "data.bin")
INVENTORY=os.path.join(os.path.dirname(__file__), "inventory.bin")

# Food and Meal database
# A single binary file holding a json list of serialized food and meal objects.
# Each object carries a "type" field ("food" or "meal") so it can be rebuilt
# into the right class on load. Names are unique: re-adding an existing name
# replaces the old entry, and meals reference their ingredients by name.

def write_json_to_bin(json_list, db=FOOD_AND_MEALS) :
    json_str = json.dumps(json_list)
    with open(db, "wb") as f:
        f.write(json_str.encode('utf-8'))


def read_json_from_bin(db=FOOD_AND_MEALS) :
    try :
        with open(db, "rb") as f :
            binary = f.read()
    except FileNotFoundError :
        return []
    if not binary :
        return []
    return json.loads(binary.decode('utf-8'))

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
    names = []
    unique_objects = []
    combined = list(reversed(dat1)) + list(reversed(dat2))

    for obj in combined :
        if obj.name not in names :
            names.append(obj.name)
            unique_objects.append(obj)
    return unique_objects

def add_to_bin(item, db=FOOD_AND_MEALS) :
    old_db = read_json_from_bin()
    old_db.append(item)
    new_db = objects_to_jsons(jsons_to_objects(old_db)) # ensures no duplicates
    write_json_to_bin(new_db, db)        
    return


        
def main() :
    apple = Food("apple", ["cub, target, walmart, co-op"], 2.0, 40, 2, 0, 1, "Honeycrisp apple")
    crust = Food("pie crust", ["cub", "target"], 3.99, 100, 20, 4, 5, "Sweet-Butter pie crust")
    apple2 = Food("apple", ["co-op"], 3.99, 40, 2, 0, 1, "Grannysmith apple")

    apple_pie = Meal("apple pie", [apple, apple, apple, crust], desc="an apple pie")
    
    print("===================")
    print("Adding to bin\n")


    add_to_bin(apple.to_json())
    add_to_bin(crust.to_json())
    add_to_bin(apple_pie.to_json())
    add_to_bin(apple2.to_json())

    loaded_data = read_json_from_bin()
    loaded_food,loaded_meals = jsons_to_objects(loaded_data)

    print(loaded_data)

    print("\n\n===================================\nFoods and Meals")
    for food in loaded_food :
        print(food)
    
    for meal in loaded_meals :
        print(meal)
        for fo in meal.foods :
            for i in range(meal.foods[fo]) :
                print(f"\t-{fo}")

    # rice = Food("rice", ["cub, target, walmart, co-op"], 13.99, 100, 30, 5, 1, "jasmine rice")
    # pizza_crust = Food("pie crust", ["cub", "target"], 3.99, 100, 20, 3, 2, "pizza dough")

    # mystery_meal = Meal("nonsense", [rice, apple, pizza_crust, crust], {}, "an apple pie")

    # new_foods = loaded_data[0]
    # new_meals = loaded_data[1]

    # new_foods.append(rice)
    # new_foods.append(pizza_crust)
    # new_meals.append(mystery_meal)

    # print("adding new items to db")
    # # add_to_db([new_foods, new_meals])

    # rm_from_db("apple")

    # print("=============================")
    # print("reading db\n")
    # for item in read_db() :
    #     for ele in item :
    #         print(ele)



if __name__ == "__main__" :
    main()