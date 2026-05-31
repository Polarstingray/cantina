'''
spending.py
    Persistent record of money spent on groceries. Each entry captures
    {id, ts, name, qty, unit_cost, total, source}. Source tags where
    the purchase originated: "checkoff" (from grocery list), "stock"
    (from inventory stock-add), or "manual" (typed into the spending page).

    Reuses grocery.py's locked + atomic + backed-up read/write helpers.
    Same persistence pattern as inventory.py and shopping.py.
'''

import os
from datetime import datetime, timezone, timedelta

from grocery import read_json_from_bin, write_json_to_bin

SPENDING = os.path.join(os.path.dirname(__file__), "spending.bin")
ALLOWED_SOURCES = ("checkoff", "stock", "manual")


# --- persistence -----------------------------------------------------------

def read_entries_raw(db=SPENDING) :
    data = read_json_from_bin(db)
    if not data :          # read_json_from_bin returns [] on missing/empty
        return []
    return data

def _write(entries, db=SPENDING) :
    write_json_to_bin(entries, db)


# --- queries ---------------------------------------------------------------

def _parse_date(s) :
    # Accept "YYYY-MM-DD" or full ISO. Returns aware UTC datetime, or None.
    if not s :
        return None
    try :
        if len(s) == 10 :       # date-only -> start of that day UTC
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError :
        return None

def read_entries(since=None, until=None, db=SPENDING) :
    """Return entries (newest first), optionally filtered by ISO dates."""
    entries = list(read_entries_raw(db))
    s = _parse_date(since)
    u = _parse_date(until)
    if s or u :
        out = []
        for e in entries :
            ts = _parse_date(e.get("ts"))
            if ts is None : continue
            if s and ts < s : continue
            if u and ts > u : continue
            out.append(e)
        entries = out
    entries.sort(key=lambda e : e.get("ts", ""), reverse=True)
    return entries


# --- mutations -------------------------------------------------------------

def add_entry(name, qty, unit_cost, source="manual", db=SPENDING) :
    if source not in ALLOWED_SOURCES :
        source = "manual"
    if qty <= 0 or unit_cost < 0 :
        return None
    entries = read_entries_raw(db)
    next_id = (max((e.get("id", 0) for e in entries), default=0)) + 1
    entry = {
        "id": next_id,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "name": name,
        "qty": float(qty),
        "unit_cost": float(unit_cost),
        "total": float(qty) * float(unit_cost),
        "source": source,
    }
    entries.append(entry)
    _write(entries, db)
    return entry


def delete_entry(entry_id, db=SPENDING) :
    entries = read_entries_raw(db)
    new_entries = [e for e in entries if e.get("id") != entry_id]
    if len(new_entries) == len(entries) :
        return -1
    _write(new_entries, db)
    return 0


# --- aggregates ------------------------------------------------------------

def totals_by_week(weeks=12, db=SPENDING) :
    """Last `weeks` ISO weeks ending this week. Returns {YYYY-Www: total}.
    Empty weeks get a 0 so the chart has a continuous x-axis."""
    now = datetime.now(timezone.utc)
    buckets = {}
    for i in range(weeks) :
        d = now - timedelta(weeks=i)
        y, w, _ = d.isocalendar()
        buckets[f"{y}-W{w:02d}"] = 0.0
    for e in read_entries_raw(db) :
        ts = _parse_date(e.get("ts"))
        if ts is None : continue
        y, w, _ = ts.isocalendar()
        key = f"{y}-W{w:02d}"
        if key in buckets :
            buckets[key] += float(e.get("total", 0))
    # newest-last order so the chart reads left-to-right oldest -> newest
    return dict(sorted(buckets.items()))


def totals_by_month(months=12, db=SPENDING) :
    now = datetime.now(timezone.utc)
    buckets = {}
    for i in range(months) :
        # walk back i months by trimming day to 1
        y = now.year
        m = now.month - i
        while m <= 0 :
            m += 12
            y -= 1
        buckets[f"{y}-{m:02d}"] = 0.0
    for e in read_entries_raw(db) :
        ts = _parse_date(e.get("ts"))
        if ts is None : continue
        key = f"{ts.year}-{ts.month:02d}"
        if key in buckets :
            buckets[key] += float(e.get("total", 0))
    return dict(sorted(buckets.items()))
