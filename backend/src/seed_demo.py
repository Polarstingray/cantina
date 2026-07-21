'''
seed_demo.py
    Paint a FABRICATED "lived-in" cantina for the public demo. None of this is
    real household data — it's an invented family so anyone can click around a
    populated app (catalog, inventory, a meal, a grocery list, weeks of spending)
    without seeing anyone's actual groceries or money.

    Honors CANTINA_DATA_DIR like the rest of the app, so it seeds whatever DB the
    server will read. Run from backend/src/ (the demo entrypoint does this):

        CANTINA_DATA_DIR=/data/demo python -m seed_demo --force

    Data is added through the app's own HTTP API (via an in-process TestClient),
    exactly as the frontend would — so the seed can't drift from the real
    contract. Spending is written with backdated timestamps so the weekly/monthly
    charts have history to show.

    Login for the demo (override with DEMO_EMAIL / DEMO_PASSWORD):
        demo@cantina.local / demopass123
'''

import os
import sys
from datetime import datetime, timedelta, timezone

import config          # resolves CANTINA_DATA_DIR at import — must come first
import db
import auth
import spending
from fastapi.testclient import TestClient

# The CSRF middleware requires this header on state-changing requests; the
# frontend sends it on every call, so the seed does too.
CSRF = {"X-Requested-With": "cantina"}

DEMO_EMAIL = os.environ.get("DEMO_EMAIL", "demo@cantina.local")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demopass123")

# A fixed "now" keeps the seeded spending history deterministic across boots.
NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)

# --- the fabricated dataset -------------------------------------------------

FOODS = [
    # name, category, cost, cals, carbs, protein, fat, brand
    ("Bananas",        "Produce", 0.29,  105, 27.0, 1.3, 0.4, ""),
    ("Baby_Spinach",   "Produce", 2.49,   23,  3.6, 2.9, 0.4, "Nature's Best"),
    ("Roma_Tomatoes",  "Produce", 1.79,   22,  4.8, 1.1, 0.2, ""),
    ("Whole_Milk",     "Dairy",   3.49,  149, 12.0, 8.0, 8.0, "Meadow Farm"),
    ("Large_Eggs",     "Dairy",   4.19,   72,  0.4, 6.3, 5.0, "Sunrise"),
    ("Cheddar",        "Dairy",   5.99,  113,  0.9, 7.0, 9.3, "Tillamook"),
    ("White_Rice",     "Pantry",  0.89,  205, 45.0, 4.3, 0.4, ""),
    ("Olive_Oil",      "Pantry",  8.99,  119,  0.0, 0.0, 14.0, "Bertolli"),
    ("Black_Beans",    "Pantry",  0.99,  114, 20.0, 7.6, 0.5, "Goya"),
    ("Chicken_Breast", "Protein", 6.49,  165,  0.0, 31.0, 3.6, ""),
    ("Ground_Beef",    "Protein", 7.29,  250,  0.0, 26.0, 15.0, ""),
    ("Almonds",        "Snacks",  9.49,  164,  6.1, 6.0, 14.0, "Blue Diamond"),
]

# name -> on-hand quantity
INVENTORY = {
    "Whole_Milk": 2, "Large_Eggs": 12, "White_Rice": 3,
    "Chicken_Breast": 2, "Bananas": 6, "Olive_Oil": 1,
}

# A meal built from catalog foods: name -> {food: amount}
MEALS = [
    ("Chicken_Rice_Bowl", {"Chicken_Breast": 1, "White_Rice": 1, "Baby_Spinach": 1},
     "Weeknight staple", "Dinner"),
]

# grocery list: name -> amount
SHOPPING = {"Roma_Tomatoes": 4, "Cheddar": 1, "Almonds": 2, "Black_Beans": 3}

# Weeks-ago -> list of (name, qty, unit_cost) purchases, for a spanning chart.
SPENDING_HISTORY = {
    7: [("Whole_Milk", 2, 3.49), ("Large_Eggs", 1, 4.19), ("Chicken_Breast", 2, 6.49)],
    6: [("White_Rice", 3, 0.89), ("Olive_Oil", 1, 8.99), ("Bananas", 6, 0.29)],
    5: [("Ground_Beef", 2, 7.29), ("Cheddar", 1, 5.99)],
    4: [("Baby_Spinach", 2, 2.49), ("Roma_Tomatoes", 4, 1.79), ("Almonds", 1, 9.49)],
    3: [("Whole_Milk", 2, 3.49), ("Large_Eggs", 2, 4.19)],
    2: [("Chicken_Breast", 3, 6.49), ("Black_Beans", 4, 0.99)],
    1: [("Bananas", 5, 0.29), ("Whole_Milk", 1, 3.49), ("Cheddar", 1, 5.99)],
    0: [("Ground_Beef", 1, 7.29), ("White_Rice", 2, 0.89)],
}


def _wipe_data_dir() :
    '''--force: drop the existing demo DB (+ WAL sidecars and legacy .bin) so the
    next access rebuilds an empty schema, mirroring the test harness.'''
    d = config.DATA_DIR
    if not os.path.isdir(d) :
        return
    for name in os.listdir(d) :
        if name.endswith((".db", ".bin")) or ".db-" in name or ".bin.bak" in name :
            try : os.remove(os.path.join(d, name))
            except OSError : pass
    db.reset()


def _seed_spending() :
    '''Write backdated spending directly (the API timestamps 'now', but the demo
    wants weeks of history for the charts).'''
    entries = []
    eid = 1
    for weeks_ago in sorted(SPENDING_HISTORY, reverse=True) :
        ts = (NOW - timedelta(weeks=weeks_ago)).isoformat()
        for name, qty, unit_cost in SPENDING_HISTORY[weeks_ago] :
            entries.append({
                "id": eid, "ts": ts, "name": name, "qty": float(qty),
                "unit_cost": float(unit_cost), "total": round(qty * unit_cost, 2),
                "source": "manual",
            })
            eid += 1
    spending._write(entries)


def main() :
    force = "--force" in sys.argv[1:]
    if force :
        _wipe_data_dir()

    db.ensure_initialized()

    # A demo admin plus a household member, so the app doesn't look single-user.
    import api  # noqa: E402 — imported after config/env are settled
    if not auth.list_users(db.HOUSEHOLD_ID) :
        auth.create_user(DEMO_EMAIL, DEMO_PASSWORD, role="admin", household_id=db.HOUSEHOLD_ID)
        auth.create_user("alex@cantina.local", "alexpass123", role="member",
                         household_id=db.HOUSEHOLD_ID)

    client = TestClient(api.app, headers=CSRF)
    r = client.post("/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    r.raise_for_status()

    # Catalog.
    for name, cat, cost, cals, carbs, prot, fat, brand in FOODS :
        client.post("/foods", json={
            "name": name, "category": cat, "cost": cost, "cals": cals,
            "carbs": carbs, "protein": prot, "fat": fat, "brand": brand,
        }).raise_for_status()

    # A meal built from those foods.
    for name, foods, desc, cat in MEALS :
        client.post("/meals", json={"name": name, "foods": foods,
                                    "desc": desc, "category": cat}).raise_for_status()

    # On-hand inventory.
    for name, amount in INVENTORY.items() :
        client.post("/inventory/add", json={"name": name, "amount": amount,
                                            "kind": "food"}).raise_for_status()

    # Grocery list.
    for name, amount in SHOPPING.items() :
        client.post("/list/add", json={"name": name, "amount": amount}).raise_for_status()

    # Backdated spending history (direct, not via the API — see _seed_spending).
    _seed_spending()

    print(f"[seed_demo] Seeded fabricated dataset into {config.DATA_DIR}")
    print(f"[seed_demo] Login: {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__" :
    main()
