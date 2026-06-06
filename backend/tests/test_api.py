'''
Characterization tests: pin the current HTTP behavior of the JSON-.bin app so
the upcoming SQLite migration can be proven behavior-preserving (the same tests
must stay green against the new storage). Happy paths plus the key rejections.
'''


# --- catalog: foods --------------------------------------------------------

def test_foods_empty_then_add_list_delete(client) :
    assert client.get("/foods").json() == []

    r = client.post("/foods", json={"name": "eggs", "cost": 4.5, "cals": 70})
    assert r.status_code == 200 and r.json() == {"ok": True}

    foods = client.get("/foods").json()
    assert [f["name"] for f in foods] == ["eggs"]
    # to_json stringifies numbers; pin that shape.
    assert foods[0]["cost"] == "4.5"
    assert foods[0]["macros"][0] == "70"

    assert client.delete("/foods/eggs").status_code == 200
    assert client.get("/foods").json() == []
    # deleting again is a 404
    assert client.delete("/foods/eggs").status_code == 404


def test_put_food_replaces_and_requires_matching_name(client) :
    client.post("/foods", json={"name": "milk", "cost": 2.0})
    r = client.put("/foods/milk", json={"name": "milk", "cost": 3.0})
    assert r.status_code == 200
    assert client.get("/foods").json()[0]["cost"] == "3.0"

    # path name and body name must agree
    bad = client.put("/foods/milk", json={"name": "soy", "cost": 1.0})
    assert bad.status_code == 400


def test_food_name_validation_rejects_slashes(client) :
    assert client.post("/foods", json={"name": "a/b"}).status_code == 422


# --- catalog: meals --------------------------------------------------------

def test_meal_requires_known_foods_then_lists(client) :
    # unknown ingredient is rejected
    assert client.post("/meals", json={"name": "x", "foods": {"ghost": 1}}).status_code == 400

    client.post("/foods", json={"name": "pasta"})
    client.post("/foods", json={"name": "eggs"})
    r = client.post("/meals", json={"name": "carbonara", "foods": {"pasta": 2, "eggs": 2}})
    assert r.status_code == 200

    meals = client.get("/meals").json()
    assert [m["name"] for m in meals] == ["carbonara"]
    assert meals[0]["foods"] == {"pasta": 2, "eggs": 2}

    # /catalog/uses reports meals referencing a food
    assert client.get("/catalog/uses/pasta").json() == ["carbonara"]


# --- inventory -------------------------------------------------------------

def test_inventory_add_autocreates_food_and_remove_guards(client) :
    # stocking an unknown food auto-creates a catalog entry
    assert client.post("/inventory/add", json={"name": "eggs", "amount": 3}).status_code == 200
    assert any(f["name"] == "eggs" for f in client.get("/foods").json())

    inv = client.get("/inventory").json()
    assert inv == {"foods": {"eggs": 3}, "meals": {}}

    assert client.post("/inventory/remove", json={"name": "eggs", "amount": 1}).status_code == 200
    assert client.get("/inventory").json()["foods"]["eggs"] == 2

    # cannot remove more than on hand (no clamping)
    assert client.post("/inventory/remove", json={"name": "eggs", "amount": 99}).status_code == 400


def test_deleting_food_drops_inventory(client) :
    client.post("/inventory/add", json={"name": "eggs", "amount": 2})
    client.delete("/foods/eggs")
    assert client.get("/inventory").json()["foods"] == {}


# --- shopping list ---------------------------------------------------------

def test_list_add_then_check_off_moves_to_inventory(client) :
    assert client.post("/list/add", json={"name": "milk", "amount": 2}).status_code == 200
    assert client.get("/list").json() == {"milk": 2}

    r = client.post("/list/check", json={"name": "milk"})
    assert r.status_code == 200 and r.json() == {"moved": 2}
    # checked-off item leaves the list and lands in inventory
    assert client.get("/list").json() == {}
    assert client.get("/inventory").json()["foods"]["milk"] == 2

    # checking off a missing item is a 404
    assert client.post("/list/check", json={"name": "nope"}).status_code == 404


# --- menu ------------------------------------------------------------------

def test_menu_buildable_and_make_consumes_ingredients(client) :
    client.post("/foods", json={"name": "pasta"})
    client.post("/foods", json={"name": "eggs"})
    client.post("/meals", json={"name": "carbonara", "foods": {"pasta": 2, "eggs": 2}})

    # nothing on hand -> 0 buildable
    assert client.get("/menu").json() == {"carbonara": 0}

    client.post("/inventory/add", json={"name": "pasta", "amount": 4})
    client.post("/inventory/add", json={"name": "eggs", "amount": 2})
    assert client.get("/menu").json() == {"carbonara": 1}

    assert client.post("/menu/make/carbonara").status_code == 200
    # one serving consumed its ingredient foods
    assert client.get("/inventory").json()["foods"] == {"pasta": 2}

    # making it again is rejected (not enough eggs)
    assert client.post("/menu/make/carbonara").status_code == 400
    # unknown meal -> 404
    assert client.post("/menu/make/ghost").status_code == 404


# --- spending --------------------------------------------------------------

def test_spending_add_list_totals_delete(client) :
    assert client.get("/spending").json() == []

    entry = client.post("/spending", json={"name": "eggs", "qty": 12, "unit_cost": 4.5}).json()
    assert entry["id"] == 1
    assert entry["total"] == 54.0
    assert entry["source"] == "manual"

    assert len(client.get("/spending").json()) == 1

    # weekly totals bucket the spend; the current week should reflect 54.0
    totals = client.get("/spending/totals", params={"bucket": "week"}).json()
    assert any(abs(v - 54.0) < 1e-9 for v in totals.values())

    # convenience source endpoints tag the entry
    from_stock = client.post("/spending/from-stock-add",
                             json={"name": "milk", "qty": 1, "unit_cost": 2.0}).json()
    assert from_stock["source"] == "stock"

    assert client.delete("/spending/1").status_code == 200
    assert client.delete("/spending/999").status_code == 404
