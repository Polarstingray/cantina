'''
db.py
    SQLite storage for cantina. Owns the schema, the connection helper, and the
    one-time importer that loads the legacy JSON .bin files into tables.

    The data modules (grocery/inventory/shopping/spending) keep their public
    function signatures; only their low-level read/write helpers route through
    here. That keeps api.py, menu.py, and the frontend untouched by the move
    off flat files.

    Multi-tenancy groundwork: every data table carries a household_id, defaulted
    to HOUSEHOLD_ID (1) for now. Phase 2 (auth) threads a real household id in;
    the schema and queries are already shaped for it.

    WAL mode + a busy timeout let concurrent readers and a single writer coexist,
    which lifts the old "one uvicorn worker only" constraint of the file backend.
'''

import contextvars
import json
import os
import sqlite3
import threading
from contextlib import contextmanager

import config

DB_PATH = config.data_path("cantina.db")

# The default household. Seeded data and the legacy import live here; it is also
# the fallback when no request has scoped a household (CLI tools, tests).
HOUSEHOLD_ID = 1

# Request-scoped current household. The auth dependency sets this per request
# (see auth.get_current_user); every data query reads current_household_id() so
# one household's rows are never visible to another. ContextVars are isolated
# per asyncio task / per worker-thread context, so this is concurrency-safe.
_current_household = contextvars.ContextVar("current_household", default=HOUSEHOLD_ID)

def current_household_id() :
    return _current_household.get()

def set_current_household(household_id) :
    _current_household.set(household_id)


SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS households (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL DEFAULT 'home',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id  INTEGER NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Server-side sessions: a random opaque token in an httponly cookie maps to a
-- user. Revocable (delete the row) and carries no secret, unlike a signed JWT.
CREATE TABLE IF NOT EXISTS sessions (
    token        TEXT    PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at   TEXT    NOT NULL,        -- ultimate (absolute) cap
    last_used_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))  -- idle clock
);

CREATE TABLE IF NOT EXISTS foods (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id INTEGER NOT NULL DEFAULT 1 REFERENCES households(id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    stores       TEXT    NOT NULL DEFAULT 'null',   -- JSON (list or null)
    cost         REAL    NOT NULL DEFAULT 0,
    cals         INTEGER NOT NULL DEFAULT 0,
    carbs        REAL    NOT NULL DEFAULT 0,
    protein      REAL    NOT NULL DEFAULT 0,
    fat          REAL    NOT NULL DEFAULT 0,
    descr        TEXT    NOT NULL DEFAULT '',
    pic          TEXT,
    brand        TEXT    NOT NULL DEFAULT '',
    serving_size TEXT    NOT NULL DEFAULT '',
    barcode      TEXT    NOT NULL DEFAULT '',
    fiber        REAL    NOT NULL DEFAULT 0,
    sugar        REAL    NOT NULL DEFAULT 0,
    sodium       REAL    NOT NULL DEFAULT 0,
    UNIQUE (household_id, name)
);

CREATE TABLE IF NOT EXISTS meals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id INTEGER NOT NULL DEFAULT 1 REFERENCES households(id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    descr        TEXT    NOT NULL DEFAULT '',
    pic          TEXT,
    UNIQUE (household_id, name)
);

-- Ingredients reference foods by NAME (not id), matching the original model:
-- a meal can list a food that isn't (or is no longer) in the catalog, and the
-- frontend warns about it rather than the row vanishing.
CREATE TABLE IF NOT EXISTS meal_ingredients (
    meal_id   INTEGER NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    food_name TEXT    NOT NULL,
    amount    REAL    NOT NULL,
    PRIMARY KEY (meal_id, food_name)
);

CREATE TABLE IF NOT EXISTS inventory (
    household_id INTEGER NOT NULL DEFAULT 1 REFERENCES households(id) ON DELETE CASCADE,
    kind         TEXT    NOT NULL CHECK (kind IN ('food', 'meal')),
    name         TEXT    NOT NULL,
    qty          REAL    NOT NULL,
    PRIMARY KEY (household_id, kind, name)
);

CREATE TABLE IF NOT EXISTS shopping (
    household_id INTEGER NOT NULL DEFAULT 1 REFERENCES households(id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    amount       REAL    NOT NULL,
    PRIMARY KEY (household_id, name)
);

-- id is per-household (add_entry assigns max+1 within the household), so the
-- primary key is composite. Two households can both have a spending entry id=1.
CREATE TABLE IF NOT EXISTS spending (
    household_id INTEGER NOT NULL DEFAULT 1 REFERENCES households(id) ON DELETE CASCADE,
    id           INTEGER NOT NULL,
    ts           TEXT    NOT NULL,
    name         TEXT    NOT NULL,
    qty          REAL    NOT NULL,
    unit_cost    REAL    NOT NULL,
    total        REAL    NOT NULL,
    source       TEXT    NOT NULL,
    PRIMARY KEY (household_id, id)
);
'''


_initialized = False
_init_lock = threading.Lock()


def _raw_connect() :
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _migrate(conn) :
    '''Additive, idempotent schema migrations for databases created by an older
    version (CREATE TABLE IF NOT EXISTS won't add columns to an existing table).'''
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
    if "last_used_at" not in cols :
        # New column on an existing sessions table. No DEFAULT (ALTER can't use a
        # non-constant default); seed existing rows from created_at.
        conn.execute("ALTER TABLE sessions ADD COLUMN last_used_at TEXT")
        conn.execute("UPDATE sessions SET last_used_at = created_at WHERE last_used_at IS NULL")


def _init() :
    conn = _raw_connect()
    try :
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.execute("INSERT OR IGNORE INTO households (id, name) VALUES (1, 'home')")
        # Import the legacy .bin files exactly once, the first time we see a
        # fresh database. The flag makes it idempotent even if the household
        # later empties everything out.
        if conn.execute("SELECT 1 FROM meta WHERE key = 'legacy_imported'").fetchone() is None :
            _import_legacy(conn)
            conn.execute("INSERT INTO meta (key, value) VALUES ('legacy_imported', '1')")
        conn.commit()
    finally :
        conn.close()
    # The database holds password hashes and live session tokens: keep it
    # owner-only (umask in config.py covers fresh files; this fixes existing 0644).
    for path in (DB_PATH, DB_PATH + "-wal", DB_PATH + "-shm") :
        try :
            os.chmod(path, 0o600)
        except OSError :
            pass


def ensure_initialized() :
    global _initialized
    if _initialized :
        return
    with _init_lock :
        if _initialized :
            return
        _init()
        _initialized = True


@contextmanager
def get_conn() :
    '''Yield a connection inside a transaction: commit on success, roll back on
    error. Open/close per use so handlers running in FastAPI's threadpool never
    share a connection across threads.'''
    ensure_initialized()
    conn = _raw_connect()
    try :
        yield conn
        conn.commit()
    except Exception :
        conn.rollback()
        raise
    finally :
        conn.close()


def reset() :
    '''Test hook: forget that we initialized so the next access rebuilds the
    schema. Pair with deleting the db file for a clean slate between tests.'''
    global _initialized
    _initialized = False


# --- legacy import ---------------------------------------------------------

def _read_legacy(filename) :
    '''Load one legacy .bin (JSON) file, or None if missing/empty.'''
    path = config.data_path(filename)
    try :
        with open(path, "rb") as f :
            raw = f.read()
    except FileNotFoundError :
        return None
    if not raw :
        return None
    try :
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) :
        return None


def _import_legacy(conn) :
    '''Best-effort one-time load of the flat-file data into the tables. Runs
    inside the caller's transaction. Foods are normalized through Food.create
    so numbers/strings land in the same shape the API already round-trips.'''
    from foods import Food  # local import: foods.py has no db dependency

    catalog = _read_legacy("data.bin") or []
    for obj in catalog :
        if obj.get("type") == "food" :
            food = Food.create(obj)
            if food :
                insert_food(conn, food)
        elif obj.get("type") == "meal" and obj.get("name") :
            insert_meal(conn, obj.get("name"), obj.get("desc") or "",
                        obj.get("pic"), obj.get("foods") or {})

    inv = _read_legacy("inventory.bin") or {}
    for kind, section in (("food", inv.get("foods") or {}), ("meal", inv.get("meals") or {})) :
        for name, qty in section.items() :
            conn.execute(
                "INSERT OR REPLACE INTO inventory (household_id, kind, name, qty) VALUES (?, ?, ?, ?)",
                (HOUSEHOLD_ID, kind, name, float(qty)))

    shop = _read_legacy("shopping.bin") or {}
    for name, amount in shop.items() :
        conn.execute(
            "INSERT OR REPLACE INTO shopping (household_id, name, amount) VALUES (?, ?, ?)",
            (HOUSEHOLD_ID, name, float(amount)))

    spend = _read_legacy("spending.bin") or []
    for e in spend :
        conn.execute(
            "INSERT OR REPLACE INTO spending "
            "(id, household_id, ts, name, qty, unit_cost, total, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (e.get("id"), HOUSEHOLD_ID, e.get("ts"), e.get("name"),
             float(e.get("qty", 0)), float(e.get("unit_cost", 0)),
             float(e.get("total", 0)), e.get("source", "manual")))


# --- shared catalog inserts (used by the importer and grocery.py) ----------

def insert_food(conn, food, household_id=HOUSEHOLD_ID) :
    '''Upsert a Food object into the foods table.'''
    conn.execute(
        '''INSERT INTO foods
               (household_id, name, stores, cost, cals, carbs, protein, fat,
                descr, pic, brand, serving_size, barcode, fiber, sugar, sodium)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (household_id, name) DO UPDATE SET
               stores=excluded.stores, cost=excluded.cost, cals=excluded.cals,
               carbs=excluded.carbs, protein=excluded.protein, fat=excluded.fat,
               descr=excluded.descr, pic=excluded.pic, brand=excluded.brand,
               serving_size=excluded.serving_size, barcode=excluded.barcode,
               fiber=excluded.fiber, sugar=excluded.sugar, sodium=excluded.sodium''',
        (household_id, food.name, json.dumps(food.stores), float(food.cost or 0),
         int(food.cals or 0), float(food.carbs or 0), float(food.protein or 0),
         float(food.fat or 0), food.desc or "", food.pic, food.brand or "",
         food.serving_size or "", food.barcode or "", float(food.fiber or 0),
         float(food.sugar or 0), float(food.sodium or 0)))


def insert_meal(conn, name, descr, pic, ingredients, household_id=HOUSEHOLD_ID) :
    '''Upsert a meal and replace its ingredient rows. `ingredients` is {name: amount}.'''
    conn.execute(
        '''INSERT INTO meals (household_id, name, descr, pic) VALUES (?, ?, ?, ?)
           ON CONFLICT (household_id, name) DO UPDATE SET descr=excluded.descr, pic=excluded.pic''',
        (household_id, name, descr or "", pic))
    meal_id = conn.execute(
        "SELECT id FROM meals WHERE household_id = ? AND name = ?",
        (household_id, name)).fetchone()["id"]
    conn.execute("DELETE FROM meal_ingredients WHERE meal_id = ?", (meal_id,))
    for food_name, amount in ingredients.items() :
        conn.execute(
            "INSERT OR REPLACE INTO meal_ingredients (meal_id, food_name, amount) VALUES (?, ?, ?)",
            (meal_id, food_name, float(amount)))
