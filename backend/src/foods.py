'''
food and meal objects here

food - *name, store/s, cost, macros, description, later on a picture
meal - *name, list of foods, helper functions for calculating total cost and macros
'''

class Food:
    def __init__(self, name, stores={}, cost=0.0, cals=0, carbs=0.0, prot=0.0, fat=0.0, desc="", pic=None):
        self.name = name
        self.stores = stores
        self.cost = cost
        self.cals = cals
        self.carbs = carbs
        self.protein=prot
        self.fat=fat
        self.desc = desc
        self.pic = pic


class Meal:
    def __init__(self, name, foods, stores={}, desc="", pic=None):
        self.name = name
        self.foods = foods
        self.desc = desc
        self.pic = pic


    def get_price(self) :
        total = 0.0
        for food in self.foods :
            total+= food.cost
        return total

    def get_macros(self) :
        cals = 0
        carbs = 0.0
        prot = 0.0
        fat = 0.0
        for food in self.foods :
            cals+= food.cals
            carbs+= food.carbs
            prot+= food.protein
            fat+= food.fat
        return {
            "calories" : cals,
            "carbs" : carbs,
            "protein" : prot,
            "fat" : fat
        }

def main() :
    apple = Food("apple", {"cub, target, walmart, co-op"}, 2.0, 40, 2, 0, 1, "Honeycrisp apple")
    crust = Food("pie crust", "cub, target", 3.99, 100, 20, 4, 5, "Sweet-Butter pie crust")

    apple_pie = Meal("apple pie", [apple, apple, apple, crust], {}, "an apple pie")

    print(apple_pie.get_macros())
    print(apple_pie.get_price())



main()