'''
ratelimit.py
    In-memory brute-force throttle for the login endpoint, keyed by
    (client_ip, email) with a looser per-IP cap on top. A successful login
    clears the counters.

    Single-process only (one uvicorn worker, which is our deployment). A public,
    multi-process deployment (Phase 4) needs a shared store like Redis.
'''

import os
import threading
import time

MAX_ATTEMPTS = int(os.environ.get("CANTINA_LOGIN_MAX_ATTEMPTS", "5"))
WINDOW_SECONDS = int(os.environ.get("CANTINA_LOGIN_WINDOW", str(15 * 60)))

# Trust X-Forwarded-For / CF-Connecting-IP only when explicitly behind a proxy
# (the Phase 3 tunnel). Otherwise those headers are attacker-controlled and a
# single client could forge unlimited "IPs" to dodge the limit.
TRUSTED_PROXY = os.environ.get("CANTINA_TRUSTED_PROXY", "0") == "1"

_lock = threading.Lock()
_attempts: dict[str, list[float]] = {}   # key -> failure timestamps within the window


def client_ip(request) -> str :
    if TRUSTED_PROXY :
        fwd = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
        if fwd :
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _keys(ip: str, email: str) :
    # (key, threshold): tight per (ip, email); looser per ip so one household
    # behind a shared address isn't locked out by one member's typos.
    return [(f"ipemail:{ip}|{email}", MAX_ATTEMPTS), (f"ip:{ip}", MAX_ATTEMPTS * 4)]


def _fresh(key: str, now: float) :
    times = [t for t in _attempts.get(key, ()) if now - t < WINDOW_SECONDS]
    if times :
        _attempts[key] = times
    else :
        _attempts.pop(key, None)
    return times


def retry_after(ip: str, email: str) :
    '''Seconds to wait if currently locked out, else None.'''
    now = time.time()
    with _lock :
        for key, threshold in _keys(ip, email) :
            times = _fresh(key, now)
            if len(times) >= threshold :
                return max(1, int(WINDOW_SECONDS - (now - min(times))))
    return None


def record_failure(ip: str, email: str) :
    now = time.time()
    with _lock :
        for key, _ in _keys(ip, email) :
            _attempts.setdefault(key, []).append(now)


def clear(ip: str, email: str) :
    with _lock :
        for key, _ in _keys(ip, email) :
            _attempts.pop(key, None)


def reset() :
    '''Test hook: drop all counters.'''
    with _lock :
        _attempts.clear()
