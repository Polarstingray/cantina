'''
Schema-migration tests. The Wyse runs a database created before later columns
existed, so `db._migrate` must add them non-destructively on the next start.
These build an old-shape table by hand and assert the migration backfills.
'''

import sqlite3

import db


def test_category_migration_adds_column_to_existing_foods_and_meals() :
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Old schema: foods/meals without `category`; sessions already current so the
    # earlier migration branch is a no-op here.
    conn.execute("CREATE TABLE sessions (token TEXT PRIMARY KEY, created_at TEXT, last_used_at TEXT)")
    conn.execute("CREATE TABLE foods (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE meals (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO foods (name) VALUES ('apple')")
    conn.execute("INSERT INTO meals (name) VALUES ('soup')")

    db._migrate(conn)

    fcols = {r["name"] for r in conn.execute("PRAGMA table_info(foods)")}
    mcols = {r["name"] for r in conn.execute("PRAGMA table_info(meals)")}
    assert "category" in fcols and "category" in mcols
    # existing rows backfill to '' (not NULL), preserving the data
    assert conn.execute("SELECT category FROM foods WHERE name='apple'").fetchone()["category"] == ""
    assert conn.execute("SELECT category FROM meals WHERE name='soup'").fetchone()["category"] == ""

    # idempotent: a second run must not error or duplicate the column
    db._migrate(conn)
    assert sum(1 for r in conn.execute("PRAGMA table_info(foods)") if r["name"] == "category") == 1
