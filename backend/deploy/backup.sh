#!/usr/bin/env bash
#
# backup.sh
#   Off-host-friendly snapshot of the cantina data directory. grocery.py keeps
#   3 in-place .bak rotations, but those die with the disk -- this writes a
#   timestamped tarball to a separate BACKUP_DIR (point it at an external drive
#   or a synced folder) and prunes to the newest KEEP archives.
#
#   Safe to run while the server is up: the .bin files are written atomically
#   (tmp file + fsync + os.replace), and the sqlite database is snapshotted via
#   sqlite3's online-backup command (".backup"), which takes a consistent copy
#   even mid-write under WAL mode. A plain cp/tar of a live WAL database is NOT
#   consistent -- never bypass the .backup step.
#
#   Env (all optional):
#     CANTINA_DATA_DIR    where the data lives   (default: backend/src)
#     CANTINA_BACKUP_DIR  where snapshots go      (default: $HOME/cantina-backups)
#     CANTINA_BACKUP_KEEP how many to retain      (default: 14)
#
set -euo pipefail

# Backups contain the database (password hashes + session tokens): owner-only.
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${CANTINA_DATA_DIR:-$SCRIPT_DIR/../src}"
BACKUP_DIR="${CANTINA_BACKUP_DIR:-$HOME/cantina-backups}"
KEEP="${CANTINA_BACKUP_KEEP:-14}"

if [ ! -d "$DATA_DIR" ] ; then
    echo "backup.sh: data dir not found: $DATA_DIR" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="$BACKUP_DIR/cantina-$stamp.tar.gz"

# Stage the snapshot in a scratch dir: legacy .bin files (already atomic on
# disk) plus a consistent copy of cantina.db taken with sqlite3's online-backup
# command. Skip the in-place .bak rotations and .tmp scratch files.
staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT

cd "$DATA_DIR"
for f in *.bin ; do
    [ -e "$f" ] && cp "$f" "$staging/"
done
if [ -f cantina.db ] ; then
    if command -v sqlite3 >/dev/null 2>&1 ; then
        sqlite3 cantina.db ".backup '$staging/cantina.db'"
    else
        # No sqlite3 CLI: python3 is always present (the app runs on it) and
        # its sqlite3 module exposes the same online-backup API.
        python3 - "$PWD/cantina.db" "$staging/cantina.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
with dst :
    src.backup(dst)
dst.close() ; src.close()
PY
    fi
fi

files="$(ls "$staging" 2>/dev/null || true)"
if [ -z "$files" ] ; then
    echo "backup.sh: no data files in $DATA_DIR -- nothing to back up" >&2
    exit 0
fi

tar -czf "$archive" -C "$staging" .
echo "backup.sh: wrote $archive"

# Retention: keep the newest $KEEP archives, delete the rest.
ls -1t "$BACKUP_DIR"/cantina-*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f
