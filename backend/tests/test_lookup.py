'''
Unit tests for lookup.py's OpenFoodFacts -> FoodIn mapping. No network: we feed
_map_off_to_food a synthetic payload and pin the rounding that keeps prefilled
values on the add-food form's step grid (macros step="0.1") so a scanned product
can actually be saved.
'''

import lookup


def _payload(nutriments) :
    return {"status": 1,
            "product": {"product_name": "Test Bar", "nutriments": nutriments}}


def test_map_rounds_macros_to_one_decimal() :
    food = lookup._map_off_to_food(_payload({
        "fat_serving": 1.205,            # the reported failing case
        "carbohydrates_serving": 12.34,
        "proteins_serving": 5.678,
        "fiber_serving": 0.96,
        "sugars_serving": 9.999,
        "sodium_serving": 0.0012,        # grams -> 1.2 mg
        "energy-kcal_serving": 211.6,
    }))
    assert food["fat"] == 1.2
    assert food["carbs"] == 12.3
    assert food["protein"] == 5.7
    assert food["fiber"] == 1.0
    assert food["sugar"] == 10.0
    assert food["sodium"] == 1.2         # 0.0012 g * 1000, rounded to 1 dp
    assert food["cals"] == 212           # int, rounded

    # Every macro now lands on the form's 0.1 grid (the bug was values like 1.205
    # tripping HTML5 step validation on save).
    for key in ("carbs", "protein", "fat", "fiber", "sugar", "sodium") :
        assert round(food[key] * 10) == food[key] * 10


def test_map_missing_nutriments_default_zero() :
    food = lookup._map_off_to_food(_payload({}))
    assert food["fat"] == 0.0
    assert food["cals"] == 0
