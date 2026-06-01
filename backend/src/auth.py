'''
auth.py
    Accounts and sessions for cantina.

    - Passwords: PBKDF2-HMAC-SHA256 (stdlib hashlib), stored as
      "pbkdf2_sha256$iterations$salt_hex$hash_hex". No native build deps; argon2
      is a reasonable future upgrade.
    - Sessions: a random opaque token (server-side, in the `sessions` table) set
      as an httponly cookie. Revocable and secret-free, unlike a signed JWT.
    - get_current_user is an ASYNC dependency on purpose: it sets the request's
      household via db.set_current_household, and an async dependency runs in the
      request's task context so that value propagates into the sync endpoint and
      its sync DB calls (a sync dependency would set it in a throwaway thread
      context). It also enforces login (401) for every data route.
'''

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response

import db

SESSION_COOKIE = "cantina_session"
SESSION_TTL_DAYS = 30
PBKDF2_ITERATIONS = 600_000

# Send the cookie only over HTTPS once a tunnel/reverse proxy terminates TLS.
# Left off by default so plain-http LAN access still works (Phase 3 turns it on).
SECURE_COOKIES = os.environ.get("CANTINA_SECURE_COOKIES", "0") == "1"


# --- passwords -------------------------------------------------------------

def hash_password(password: str) -> str :
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool :
    try :
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256" :
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iters))
    except (ValueError, TypeError) :
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)


# --- users -----------------------------------------------------------------

def _norm_email(email: str) -> str :
    return (email or "").strip().lower()


def get_user_by_email(email: str) :
    with db.get_conn() as conn :
        r = conn.execute(
            "SELECT id, household_id, email, password_hash, role FROM users WHERE email = ?",
            (_norm_email(email),)).fetchone()
    return dict(r) if r else None


def create_user(email: str, password: str, role: str = "member", household_id: int | None = None) :
    '''Create a user. Raises ValueError on duplicate email or bad role. Returns the new id.'''
    if role not in ("admin", "member") :
        raise ValueError("role must be 'admin' or 'member'")
    email = _norm_email(email)
    if not email or not password :
        raise ValueError("email and password are required")
    if household_id is None :
        household_id = db.HOUSEHOLD_ID
    with db.get_conn() as conn :
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone() :
            raise ValueError(f"a user with email '{email}' already exists")
        # Make sure the household row exists (defaults to the single 'home').
        conn.execute("INSERT OR IGNORE INTO households (id, name) VALUES (?, 'home')", (household_id,))
        conn.execute(
            "INSERT INTO users (household_id, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (household_id, email, hash_password(password), role))
        return conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]


def list_users(household_id: int) :
    with db.get_conn() as conn :
        rows = conn.execute(
            "SELECT id, email, role, created_at FROM users WHERE household_id = ? ORDER BY id",
            (household_id,)).fetchall()
    return [dict(r) for r in rows]


# --- sessions --------------------------------------------------------------

def _now_iso() :
    return datetime.now(timezone.utc).isoformat()


def create_session(user_id: int) -> str :
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)).isoformat()
    with db.get_conn() as conn :
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires))
    return token


def get_session_user(token: str | None) :
    '''Return {id, household_id, email, role} for a live session, else None.'''
    if not token :
        return None
    with db.get_conn() as conn :
        r = conn.execute(
            "SELECT u.id, u.household_id, u.email, u.role, s.expires_at "
            "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
            (token,)).fetchone()
    if not r :
        return None
    if r["expires_at"] <= _now_iso() :     # same fixed ISO-UTC format -> safe lexical compare
        delete_session(token)
        return None
    return {"id": r["id"], "household_id": r["household_id"], "email": r["email"], "role": r["role"]}


def delete_session(token: str | None) :
    if not token :
        return
    with db.get_conn() as conn :
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


# --- cookie helpers --------------------------------------------------------

def set_session_cookie(response: Response, token: str) :
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_TTL_DAYS * 86400,
                        httponly=True, samesite="lax", secure=SECURE_COOKIES, path="/")


def clear_session_cookie(response: Response) :
    response.delete_cookie(SESSION_COOKIE, path="/")


# --- FastAPI dependencies --------------------------------------------------

async def get_current_user(request: Request) :
    '''Authenticate the request and scope it to the user's household. Raises 401
    if there is no valid session. Must be async so the contextvar set here is
    visible to the (sync) endpoint and its DB calls.'''
    user = get_session_user(request.cookies.get(SESSION_COOKIE))
    if not user :
        raise HTTPException(status_code=401, detail="not authenticated")
    db.set_current_household(user["household_id"])
    return user


async def require_admin(user=Depends(get_current_user)) :
    if user["role"] != "admin" :
        raise HTTPException(status_code=403, detail="admin only")
    return user
