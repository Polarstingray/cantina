#!/bin/bash
# Boot the demo: repaint a fabricated dataset, then serve the app with uvicorn
# (which also serves the static frontend). The demo DB is deliberately EPHEMERAL
# (no volume mounted) — every restart gets a clean, identical fake dataset, which
# doubles as the reset mechanism for a public instance anyone can click around in.
#
# Cantina has no SESSION_SECRET to enforce (sessions are opaque tokens stored as
# sha256 in the DB, not signed cookies), so there's no secret-gating here.
set -euo pipefail

: "${CANTINA_DATA_DIR:=/data/demo}"
mkdir -p "$CANTINA_DATA_DIR"

# Repaint the fabricated dataset (--force wipes whatever was there). Set
# DEMO_RESET=false to keep an existing DB across restarts.
if [ "${DEMO_RESET:-true}" = "true" ]; then
  echo "[demo] Seeding fabricated dataset into $CANTINA_DATA_DIR"
  # The seed logs in via an in-process TestClient over plain HTTP. With
  # CANTINA_SECURE_COOKIES=1 (set for real traffic behind Fly's TLS) the login
  # cookie comes back Secure, the HTTP client drops it, and the next authed POST
  # 401s — so run the seed with secure cookies OFF. Only this subprocess sees it;
  # uvicorn below still starts with the deployment's real settings.
  CANTINA_SECURE_COOKIES=0 CANTINA_TRUSTED_PROXY=0 python -m seed_demo --force
fi

# --proxy-headers so the app trusts the X-Forwarded-* from the host's TLS
# terminator (scheme for Secure cookies when CANTINA_SECURE_COOKIES=1).
uvicorn api:app \
  --host "${CANTINA_HOST:-0.0.0.0}" --port "${CANTINA_PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips '*' &
APP_PID=$!

# Exit status is load-bearing: Fly stops an idle machine with SIGTERM, and the
# restart policy is `on-failure` — so exiting non-zero on a *requested* shutdown
# looks like a crash and defeats scale-to-zero. A signalled shutdown exits 0;
# only the app dying on its own is a failure worth restarting for.
shutting_down=0
on_term() { shutting_down=1; kill -TERM "$APP_PID" 2>/dev/null || true; }
trap on_term TERM INT

rc=0
wait "$APP_PID" || rc=$?

if [ "$shutting_down" = "1" ]; then
  echo "[demo] Shutdown signal received; stopping cleanly."
  exit 0
fi

echo "[demo] uvicorn exited unexpectedly (rc=$rc)." >&2
exit "$rc"
