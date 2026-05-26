'''
grocery.py
    write and read from binary database (sqlite in the future) and dynamic grocery list csv
    add food items to database
    add meals to database
    keep track of a list of foods, their cost, and where to buy them
'''

import pickle
from foods import *
FOOD_AND_MEALS="./data.pkl"

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
def write_db(data, db=FOOD_AND_MEALS) :
    with open(db, 'wb+') as f:
        pickle.dump(data, f)

def unique_list(dat1, dat2) :
    names = []
    unique_objects = []
    for obj in (dat1 + dat2) :
        if obj.name not in names :
            names.append(obj.name)
            unique_objects.append(obj)
    return unique_objects

def add_to_db(data, db=FOOD_AND_MEALS) :
    if len(data) > 1 :
        curr_data = read_db(db)
        if (not curr_data) :
            write_db(((unique_list(data[0], [])), unique_list(data[1], [])))
        if (len(curr_data) > 1) :
            unique_foods = unique_list(curr_data[0], data[0])
            unique_meals = unique_list(curr_data[1], data[1])
            write_db([unique_foods, unique_meals], db)
            return 0
        else :
            print("error, corrupted db")
            return -1
    
    return -1

def read_db(db=FOOD_AND_MEALS) :
    with open(db, "rb+") as f:
        data =pickle.load(f)
    return data

def rm_from_db(name, db=FOOD_AND_MEALS) :
    foods, meals = read_db(db)

    for i in range(len(foods)) :
        if foods[i].name == name :
            foods.pop(i)
            write_db((foods, meals))
            return 0

    for i in range(len(meals)) :
        if meals[i].name == name :
            meals.pop(i)
            write_db((foods, meals))
            return 0
        
    print("Error, item not found")
    return 1

        
def main() :
    apple = Food("apple", ["cub, target, walmart, co-op"], 2.0, 40, 2, 0, 1, "Honeycrisp apple")
    crust = Food("pie crust", ["cub", "target"], 3.99, 100, 20, 4, 5, "Sweet-Butter pie crust")

    apple_pie = Meal("apple pie", [apple, apple, apple, crust], {}, "an apple pie")
    
    print("===================")
    print("reading db\n")

    foods = [apple, crust]
    meals = [apple_pie]

    # write_db([foods, meals])
    add_to_db([foods, meals])

    loaded_data = read_db()
    for item in loaded_data :
        for ele in item :
            print(ele)

    rice = Food("rice", ["cub, target, walmart, co-op"], 13.99, 100, 30, 5, 1, "jasmine rice")
    pizza_crust = Food("pie crust", ["cub", "target"], 3.99, 100, 20, 3, 2, "pizza dough")

    mystery_meal = Meal("nonsense", [rice, apple, pizza_crust, crust], {}, "an apple pie")

    new_foods = loaded_data[0]
    new_meals = loaded_data[1]

    new_foods.append(rice)
    new_foods.append(pizza_crust)
    new_meals.append(mystery_meal)

    print("adding new items to db")
    add_to_db([new_foods, new_meals])

    rm_from_db("apple")

    print("=============================")
    print("reading db\n")
    for item in read_db() :
        for ele in item :
            print(ele)



if __name__ == "__main__" :
    main()