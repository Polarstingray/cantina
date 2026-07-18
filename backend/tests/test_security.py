'''
Security-hardening tests (Phase 2.5): session idle/ultimate timeouts, login
brute-force throttle, session revocation on password change, input/length
policy, CSRF header requirement, security headers, docs lockdown, and db file
permissions.
'''

import os
import stat
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import api
import auth
import db
import ratelimit
from conftest import make_client, CSRF_HEADERS


def _now() :
    return datetime.now(timezone.utc)

def _set_session_field(token, field, value) :
    # The table stores sha256(token), so look rows up by the hash.
    with db.get_conn() as conn :
        conn.execute(f"UPDATE sessions SET {field} = ? WHERE token = ?",
                     (value, auth._hash_token(token)))


# --- session timeouts ------------------------------------------------------

def test_idle_timeout_logs_out(client) :
    assert client.get("/auth/me").status_code == 200
    token = client.cookies.get(auth.COOKIE_NAME)
    # Backdate last activity beyond the idle window.
    stale = (_now() - timedelta(seconds=auth.SESSION_IDLE_SECONDS + 60)).isoformat()
    _set_session_field(token, "last_used_at", stale)
    assert client.get("/auth/me").status_code == 401


def test_ultimate_timeout_logs_out(client) :
    token = client.cookies.get(auth.COOKIE_NAME)
    _set_session_field(token, "expires_at", (_now() - timedelta(seconds=5)).isoformat())
    assert client.get("/auth/me").status_code == 401


def test_active_session_slides_and_survives(client) :
    # A recent-but-not-stale session keeps working, and last_used_at moves forward.
    token = client.cookies.get(auth.COOKIE_NAME)
    recent = (_now() - timedelta(seconds=60)).isoformat()
    _set_session_field(token, "last_used_at", recent)
    assert client.get("/auth/me").status_code == 200
    with db.get_conn() as conn :
        after = conn.execute("SELECT last_used_at FROM sessions WHERE token = ?",
                             (auth._hash_token(token),)).fetchone()["last_used_at"]
    assert after > recent


# --- brute-force throttle --------------------------------------------------

def test_login_brute_force_locks_out(anon_client) :
    auth.create_user("brute@home", "correct-horse-battery", role="admin", household_id=1)
    for _ in range(ratelimit.MAX_ATTEMPTS) :   # first MAX_ATTEMPTS bad tries -> 401
        r = anon_client.post("/auth/login", json={"email": "brute@home", "password": "wrongpass!!"})
        assert r.status_code == 401
    # the next one is throttled
    r = anon_client.post("/auth/login", json={"email": "brute@home", "password": "wrongpass!!"})
    assert r.status_code == 429 and "retry-after" in {k.lower() for k in r.headers}


# --- password change revokes sessions --------------------------------------

def test_password_change_revokes_sessions(client) :
    assert client.get("/auth/me").status_code == 200
    auth.set_password("test@home", "a-brand-new-password")
    assert client.get("/auth/me").status_code == 401   # old cookie no longer valid


def test_logout_all_revokes_other_sessions() :
    # two devices for the same user
    a = make_client("dual@home", "first-password-123", role="admin", household_id=1)
    b = TestClient(api.app, headers=CSRF_HEADERS)
    assert b.post("/auth/login", json={"email": "dual@home", "password": "first-password-123"}).status_code == 200
    assert a.post("/auth/logout-all").status_code == 200
    assert b.get("/auth/me").status_code == 401   # the other device is signed out too


# --- input / password policy -----------------------------------------------

def test_overlong_password_rejected(anon_client) :
    r = anon_client.post("/auth/login", json={"email": "x@home", "password": "a" * 201})
    assert r.status_code == 422


def test_short_password_rejected_api_and_cli() :
    admin = make_client("policy@home", "good-long-password", role="admin", household_id=1)
    assert admin.post("/auth/users", json={"email": "kid@home", "password": "short"}).status_code == 422
    with pytest.raises(ValueError) :
        auth.create_user("cli@home", "short", household_id=1)


# --- CSRF + headers + docs + file perms ------------------------------------

def test_state_change_requires_csrf_header() :
    bare = TestClient(api.app)  # no X-Requested-With
    auth.create_user("csrf@home", "csrf-password-123", role="admin", household_id=1)
    assert bare.post("/auth/login", json={"email": "csrf@home", "password": "csrf-password-123"}).status_code == 403


def test_security_headers_present(anon_client) :
    r = anon_client.get("/foods")  # 401, but the middleware still sets headers
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    csp = r.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    # WASM barcode decoder (iOS/Firefox camera scanning) needs wasm compilation;
    # the token permits WASM only, not the broader JS eval.
    assert "script-src 'self' 'wasm-unsafe-eval'" in csp
    assert "'unsafe-eval'" not in csp.replace("'wasm-unsafe-eval'", "")


def test_api_docs_disabled(anon_client) :
    assert anon_client.get("/openapi.json").status_code == 404
    assert anon_client.get("/docs").status_code == 404


def test_db_file_is_owner_only(client) :
    # `client` has triggered db init, which chmods the file to 0600.
    mode = stat.S_IMODE(os.stat(db.DB_PATH).st_mode)
    assert mode == 0o600, oct(mode)


# --- session tokens hashed at rest ------------------------------------------

def test_session_token_not_stored_in_plaintext(client) :
    token = client.cookies.get(auth.COOKIE_NAME)
    with db.get_conn() as conn :
        stored = [r["token"] for r in conn.execute("SELECT token FROM sessions")]
    assert stored, "expected a live session row"
    assert token not in stored                       # raw cookie value never at rest
    assert auth._hash_token(token) in stored         # ...only its sha256
    # and the session still works + revokes through the hashed lookup
    assert client.get("/auth/me").status_code == 200
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401


# --- rate limiter memory bound ----------------------------------------------

def test_ratelimit_prunes_stale_keys() :
    ratelimit.reset()
    old = time.time() - ratelimit.WINDOW_SECONDS - 1
    try :
        # Fill past the prune threshold with already-expired keys.
        for i in range(ratelimit._PRUNE_THRESHOLD) :
            ratelimit._attempts[f"ipemail:1.2.3.4|u{i}@x"] = [old]
        ratelimit.record_failure("5.6.7.8", "fresh@x")
        # The sweep dropped every stale key; only the fresh failure remains.
        assert len(ratelimit._attempts) == 2   # ipemail + ip key for the new failure
    finally :
        ratelimit.reset()


# --- barcode input strictness -----------------------------------------------

def test_barcode_rejects_unicode_digits(client) :
    # isdigit() alone would accept these; they must never hit the outbound URL.
    assert client.get("/lookup/barcode/٣٣٣").status_code == 400
    assert client.get("/lookup/barcode/²²").status_code == 400
