#!/usr/bin/env bash
#
# backup.sh
#   Off-host-friendly snapshot of the cantina data directory. grocery.py keeps
#   3 in-place .bak rotations, but those die with the disk -- this writes a
#   timestamped tarball to a separate BACKUP_DIR (point it at an external drive
#   or a synced folder) and prunes to the newest KEEP archives.
#
#   Safe to run while the server is up: the app writes every file atomically
#   (tmp file + fsync + os.replace), so each .bin / .db is always a complete,
#   self-consistent snapshot.
#
#   Env (all optional):
#     CANTINA_DATA_DIR    where the data lives   (default: backend/src)
#     CANTINA_BACKUP_DIR  where snapshots go      (default: $HOME/cantina-backups)
#     CANTINA_BACKUP_KEEP how many to retain      (default: 14)
#
set -euo pipefail

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

# Real data only: the .bin files today, plus data.db after the sqlite migration.
# Skip the in-place .bak rotations and .tmp scratch files.
cd "$DATA_DIR"
files="$(ls *.bin data.db 2>/dev/null || true)"
if [ -z "$files" ] ; then
    echo "backup.sh: no data files in $DATA_DIR -- nothing to back up" >&2
    exit 0
fi

# shellcheck disable=SC2086
tar -czf "$archive" $files
echo "backup.sh: wrote $archive"

# Retention: keep the newest $KEEP archives, delete the rest.
ls -1t "$BACKUP_DIR"/cantina-*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f
