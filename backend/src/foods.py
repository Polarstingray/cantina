import sys

'''
food and meal objects here

food - *name, store/s, cost, macros, description, later on a picture
meal - *name, list of foods, helper functions for calculating total cost and macros
'''

class Food:
    def __init__(self, name, stores=None, cost=0.0, cals=0, carbs=0.0, prot=0.0, fat=0.0, desc="", pic=None,
                 brand="", serving_size="", barcode="", fiber=0.0, sugar=0.0, sodium=0.0):
        self.name = name
        self.stores = stores
        self.cost = cost
        self.cals = cals
        self.carbs = carbs
        self.protein=prot
        self.fat=fat
        self.desc = desc
        self.pic = pic
        # Optional metadata (populated by barcode lookup or manual entry).
        # Existing catalog rows missing these fields load with empty defaults.
        self.brand = brand
        self.serving_size = serving_size
        self.barcode = barcode
        self.fiber = fiber
        self.sugar = sugar
        self.sodium = sodium      # in mg

    @staticmethod
    def create(food_json) :
        if food_json.get("type") != "food" or not food_json.get("name"):
            return None

        # Pad short/missing macros to 4 entries; tolerate non-numeric strings.
        raw = food_json.get("macros") or []
        def _num(x, cast) :
            try : return cast(x)
            except (TypeError, ValueError) : return cast(0)
        padded = (list(raw) + [0, 0, 0, 0])[:4]
        macros = [_num(padded[0], int),
                  _num(padded[1], float),
                  _num(padded[2], float),
                  _num(padded[3], float)]

        return Food(food_json.get("name"),
                    food_json.get("stores"),
                    _num(food_json.get("cost"), float),
                    macros[0], macros[1], macros[2], macros[3],
                    food_json.get("desc"),
                    food_json.get("pic"),
                    brand=food_json.get("brand", "") or "",
                    serving_size=food_json.get("serving_size", "") or "",
                    barcode=food_json.get("barcode", "") or "",
                    fiber=_num(food_json.get("fiber"), float),
                    sugar=_num(food_json.get("sugar"), float),
                    sodium=_num(food_json.get("sodium"), float))

    # Serialize food as json to be stored in binary and later sqlite db
    def to_json(self) :
        return {
            "type" : "food",
            "name" : self.name,
            "stores" : self.stores,
            "cost" : str(self.cost),
            "macros" : [str(self.cals), str(self.carbs), str(self.protein), str(self.fat)],
            "desc" : self.desc,
            "pic" : self.pic,
            "brand" : self.brand,
            "serving_size" : self.serving_size,
            "barcode" : self.barcode,
            "fiber" : str(self.fiber),
            "sugar" : str(self.sugar),
            "sodium" : str(self.sodium),
        }

    def __str__(self) :
        return self.name

    def __hash__(self) :
        return hash(self.name)

    def __eq__(self, other) :
        return self.name == other.name
    

class Meal:
    def __init__(self, name, foods, desc="", pic=None):
        self.name = name
        self.desc = desc
        self.pic = pic

        self.foods = {}
        if isinstance(foods, list) :
            self.add_foods(foods)
        elif isinstance(foods, Food) :
            self.foods = {foods : 1}
        else :
            self.foods = foods

    def __eq__(self, other) :
        return self.name == other.name
    
    def __hash__(self) :
        return hash(self.name)

    def get_price(self) :
        total = 0.0
        for food, amount in self.foods.items() :
            total += food.cost * amount
        return total
    
    # Rebuild a Meal from its json. Ingredients are stored by name, so each one
    # is resolved against food_catalog ({name: Food}) loaded from the database.
    @staticmethod
    def create(meal_json, food_catalog) :
        if meal_json.get("type") != "meal" or not meal_json.get("name"):
            return None
        foods = {}
        for name, amount in meal_json.get("foods").items() :
            food = food_catalog.get(name)
            if not food :
                print(f"Food '{name}' not found in database, skipping", file=sys.stderr)
                continue
            foods[food] = amount

        return Meal(meal_json.get("name"),
                    foods,
                    desc=meal_json.get("desc"),
                    pic=meal_json.get("pic"))

    # Serialize the meal; ingredients are stored as {food_name: amount} and the
    # full food details are looked up from the database on load.
    def to_json(self) :
        ingredients = {food.name : amount for food, amount in self.foods.items()}
        return {"type" : "meal",
                "name" : self.name,
                "foods": ingredients,
                "desc" : self.desc,
                "pic" : self.pic}

    def add_food(self, food, amount=1) :
        if not food :
            print("Must add a food with a name", file=sys.stderr)
            return -1
        if (amount <= 0) :
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
        if (amount <= 0) :
            print("Invalid amount to remove", file=sys.stderr)
            return -1

        if food in self.foods :
            if self.foods[food] + 1e-9 < amount :
                return -1
            else :
                self.foods[food] -= amount
        else :
            print("Food item not in meal", file=sys.stderr)
            return -1
        if self.foods[food] <= 1e-9 :
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

    apple_pie = Meal("apple pie", [apple, apple, apple, crust], desc="an apple pie")

    print(apple_pie.get_macros())
    print(apple_pie.get_price())
    for food in apple_pie.foods :
        print(f"{food} x{apple_pie.foods[food]}")


if __name__ == "__main__" :
    main()