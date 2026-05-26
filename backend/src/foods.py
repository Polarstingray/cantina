import sys

'''
food and meal objects here

food - *name, store/s, cost, macros, description, later on a picture
meal - *name, list of foods, helper functions for calculating total cost and macros
'''

class Food:
    def __init__(self, name, stores=[], cost=0.0, cals=0, carbs=0.0, prot=0.0, fat=0.0, desc="", pic=None):
        self.name = name
        self.stores = stores
        self.cost = cost
        self.cals = cals
        self.carbs = carbs
        self.protein=prot
        self.fat=fat
        self.desc = desc
        self.pic = pic

    def create(name, stores=[], cost=0.0, macros=[], desc="", pic=None) :
        return Food(name, stores, cost, macros[0], macros[1], macros[2], macros[3], desc, pic)
    
    def create(food_json) :
        if food_json.get("type") != "food" or not food_json.get("name"):
            return None

        # print(food_json.get("macros"))
        macros = [int(food_json.get("macros")[0]), 
                  float(food_json.get("macros")[1]), 
                  float(food_json.get("macros")[2]), 
                  float(food_json.get("macros")[3])]
        

        return Food(food_json.get("name"),
                    food_json.get("stores"),
                    food_json.get("cost"),
                    macros[0], macros[1], macros[2], macros[3],
                    food_json.get("desc"),
                    food_json.get("pic"))
    
    # Serialize food as json to be stored in binary and later sqlite db
    def to_json(self) :
        return {
            "type" : "food",
            "name" : self.name, 
            "stores" : self.stores, 
            "cost" : str(self.cost), 
            "macros" : [str(self.cals), str(self.carbs), str(self.protein), str(self.fat)], 
            "desc" : self.desc, 
            "pic" : self.pic
        }

    def __str__(self) :
        return self.name

    def __hash__(self) :
        # tup = tuple((self.cals+1, self.carbs, self.protein, self.fat))
        return hash(self.cals)
    def __eq__(self, other) :
        return self.name == other.name
    

class Meal:
    def __init__(self, name, foods, stores=[], desc="", pic=None):
        self.name = name
        self.desc = desc
        self.pic = pic

        self.foods = {}
        if type(foods) == list :
            self.add_foods(foods)
        elif type(foods) == Food :
            self.foods = {foods : 1}
        else :
            self.foods = foods

    def __eq__(self, other) :
        return self.name == other.name
    
    def __hash__(self) :
        macros = self.get_macros()
        return hash((macros.get("calories"), macros.get("carbs"), macros.get("protein"), macros.get("fat")))

    def get_price(self) :
        total = 0.0
        for food, amount in self.foods.items() :
            total += food.cost * amount
        return total
    
    def create(name, foods, stores=[], desc="", pic=None) :
        return Meal(name, foods, stores, desc, pic)
    
    def create(meal_json) :
        if meal_json.get("type") != "meal" or not meal_json.get("name"):
            return None
        foods = []
        for food in meal_json.get("foods") :
            foods.append(Food.create(food))

        return Meal(meal_json.get("name"),
                    foods,
                    meal_json.get("desc"),
                    meal_json.get("pic"))
    
    # This will be used to serialize meals to/from binary.
    def to_json(self) :
        food_list=[]
        for food in self.foods :
            food_list.append(food.to_json())

        out = {"type" : "meal",
                "name" : self.name, 
                "foods": food_list, 
                "desc" : self.desc, 
                "pic" : self.pic} 
        return out

    def add_food(self, food, amount=1) :
        if not food :
            print("Must add a food with a name", file=sys.stderr)
            return -1
        if (amount < 1) :
            print("Invalid amount to add", file=sys.stderr)
            return -1
        
        if food in self.foods :
            self.foods[food] += amount
        else :
            self.foods[food] = amount

    # add a list of foods, mostly just for testing 
    def add_foods(self, foods) :
        for food in foods :
            self.add_food(food)

    def remove_food(self, food, amount=1) :
        if not food :
            print("Must remove a food with a name", file=sys.stderr)
            return -1
        if (amount < 1) :
            print("Invalid amount to remove", file=sys.stderr)
            return -1
        
        if food in self.foods :
            if self.foods[food] < amount :
                self.foods[food] = 0
            else :
                self.foods[food] -= amount
        else :
            print("Food item not in meal", file=sys.stderr)
            return -1
        if self.foods[food] == 0 :
            self.foods.pop(food, None)
            print("Removing food item from ingredient list")
        return 0

    def get_macros(self) :
        cals = 0
        carbs = 0.0
        prot = 0.0
        fat = 0.0
        for food, amount in self.foods.items() :
            cals+= food.cals * amount
            carbs+= food.carbs * amount
            prot+= food.protein * amount
            fat+= food.fat * amount
        return {
            "calories" : cals,
            "carbs" : carbs,
            "protein" : prot,
            "fat" : fat
        }
    def __str__(self) :
        return self.name

def main() :
    apple = Food("apple", ["cub, target, walmart, co-op"], 2.0, 40, 2, 0, 1, "Honeycrisp apple")
    crust = Food("pie crust", ["cub", "target"], 3.99, 100, 20, 4, 5, "Sweet-Butter pie crust")

    apple_pie = Meal("apple pie", [apple, apple, apple, crust], {}, "an apple pie")

    print(apple_pie.get_macros())
    print(apple_pie.get_price())
    for food in apple_pie.foods :
        print(f"{food} x{apple_pie.foods[food]}")


if __name__ == "__main__" :
    main()