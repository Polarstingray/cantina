'''
grocery.py
    write and read from binary database (sqlite in the future) and dynamic grocery list csv
    add food items to database
    add meals to database
    keep track of a list of foods, their cost, and where to buy them
'''

import pickle
import json
from foods import *
FOOD_AND_MEALS="./data.bin"

# Food and Meal database
# binary file that stores unique food and meal objects.
# the rest is the Food/Meal object binary

# if a food/meal is already in the database, do not add again
# Add/remove foods and meals (singular)


'''
data - list of list of foods and meals
    1st list is Foods
    2nd list is Meals
'''
# def write_db(data, db=FOOD_AND_MEALS) :
#     with open(db, 'wb+') as f:
#         pickle.dump(data, f)

# writes and reads lists of serialized Meal and Food json objects
def write_json_to_bin(json_list, db=FOOD_AND_MEALS) :
    json_str = json.dumps(json_list)
    with open(db, "wb") as f:
        f.write(json_str.encode('utf-8'))


def read_json_from_bin(db=FOOD_AND_MEALS) :
    with open(db, "rb") as f :
        binary = f.read()
    if not binary :
        return []
    return json.loads(binary.decode('utf-8'))

# Returns list of a list of foods and meals from the list of food and meal json objects
def load_jsons(json_list) :
    foods = []
    meals = []
    # print("\n",json_list)
    for obj in json_list :
        if obj.get("type") and obj.get("type") == "food" :
            tmp = Food.create(obj)
            if tmp :
                foods.append(tmp)
        elif obj.get("type"):
            tmp = Meal.create(obj)
            if tmp :
                meals.append(tmp)
    return [foods, meals]


# enforces unique rule and converts 2 lists of food/meal objects to list of food/meal json object
# data is [food_list, meal_list]
def dump_jsons(data) :
    foods, meals = data
    json_list = []
    foods = unique_list(foods, [])
    for food in foods :
        json_list.append(food.to_json())

    meals = unique_list(meals, [])
    for meal in meals :
        json_list.append(meal.to_json())
    return json_list

def unique_list(dat1, dat2) :
    names = []
    unique_objects = []
    for obj in (dat1 + dat2) :
        if obj.name not in names :
            names.append(obj.name)
            unique_objects.append(obj)
    return unique_objects

def add_to_bin(item, db=FOOD_AND_MEALS) :
    old_db = read_json_from_bin()
    old_db.append(item)
    new_db = dump_jsons(load_jsons(old_db)) # ensures no duplicates
    write_json_to_bin(new_db, db)        
    return

# def add_to_db(data, db=FOOD_AND_MEALS) :
#     if len(data) > 1 :
#         curr_data = read_db(db)
#         if (not curr_data) :
#             write_db(((unique_list(data[0], [])), unique_list(data[1], [])))
#         if (len(curr_data) > 1) :
#             unique_foods = unique_list(curr_data[0], data[0])
#             unique_meals = unique_list(curr_data[1], data[1])
#             write_db([unique_foods, unique_meals], db)
#             return 0
#         else :
#             print("error, corrupted db")
#             return -1
#     return -1

# def read_db(db=FOOD_AND_MEALS) :
#     with open(db, "rb+") as f:
#         data =pickle.load(f)
#     return data

# def rm_from_db(name, db=FOOD_AND_MEALS) :
#     foods, meals = read_db(db)

#     for i in range(len(foods)) :
#         if foods[i].name == name :
#             foods.pop(i)
#             write_db((foods, meals))
#             return 0

#     for i in range(len(meals)) :
#         if meals[i].name == name :
#             meals.pop(i)
#             write_db((foods, meals))
#             return 0
        
#     print("Error, item not found")
#     return 1

        
def main() :
    apple = Food("apple", ["cub, target, walmart, co-op"], 2.0, 40, 2, 0, 1, "Honeycrisp apple")
    crust = Food("pie crust", ["cub", "target"], 3.99, 100, 20, 4, 5, "Sweet-Butter pie crust")

    apple_pie = Meal("apple pie", [apple, apple, apple, crust], [], "an apple pie")
    
    print("===================")
    print("reading db\n")


    add_to_bin(apple.to_json())
    add_to_bin(crust.to_json())
    add_to_bin(apple_pie.to_json())

    loaded_data = read_json_from_bin()
    loaded_food,loaded_meals = load_jsons(loaded_data)


    print("\n\n===================================\nFoods and Meals")
    for food in loaded_food :
        print(food)
    
    for meal in loaded_meals :
        print(meal)

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