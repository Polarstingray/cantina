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
    with open(db, 'wb') as f:
        pickle.dump(data, f)

def read_db(db=FOOD_AND_MEALS) :
    with open(db, "rb") as f:
        data =pickle.load(f)
    return data

def main() :
    apple = Food("apple", {"cub, target, walmart, co-op"}, 2.0, 40, 2, 0, 1, "Honeycrisp apple")
    crust = Food("pie crust", "cub, target", 3.99, 100, 20, 4, 5, "Sweet-Butter pie crust")

    apple_pie = Meal("apple pie", [apple, apple, apple, crust], {}, "an apple pie")

    print(apple_pie.get_macros())
    print(apple_pie.get_price())
    for food in apple_pie.foods :
        print(f"{food} x{apple_pie.foods[food]}")

    foods = [apple, crust]
    meals = [apple_pie]

    write_db([foods, meals])

    data = read_db()
    for item in data :
        for food_meal in item :
            print(food_meal)


if __name__ == "__main__" :
    main()