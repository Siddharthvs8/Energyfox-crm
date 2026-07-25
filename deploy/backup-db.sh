#!/usr/bin/env bash
# EnergyFox CRM — nightly Postgres dump to a rotated local archive.
#
#   sudo ./deploy/backup-db.sh [--dest DIR] [--keep N]
#   sudo ./deploy/backup-db.sh --verify-only FILE
#   sudo ./deploy/backup-db.sh --restore-test [FILE]   # restores into a scratch DB
#
# The dump contains every customer record in the CRM, in the clear. Archives are
# 0600 inside a 0700 directory for that reason — treat a copy of one as you would
# the database itself.
#
# Restore (see energyfox-cron.md): the dump has no DROP statements, so it is
# restored into an empty database, not over a live one.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DEST="/var/backups/energyfox"
KEEP=30
MODE="backup"
TARGET=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dest)         DEST="$2"; shift 2 ;;
        --keep)         KEEP="$2"; shift 2 ;;
        --verify-only)  MODE="verify"; TARGET="$2"; shift 2 ;;
        --restore-test) MODE="restore-test"; TARGET="${2:-}"; [[ -n "$TARGET" ]] && shift; shift ;;
        *) echo "usage: sudo $0 [--dest DIR] [--keep N] | --verify-only FILE | --restore-test [FILE]" >&2; exit 1 ;;
    esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] error: $*" >&2; exit 1; }

# Every `docker compose exec` needs </dev/null. Without it the client inherits
# this script's stdin and swallows the rest of the file when we are piped in.
dc() { docker compose exec -T db "$@" </dev/null; }

# Credentials come from the container's own environment rather than .env, so this
# keeps working if the env file is unreadable or the values change.
DB_USER="$(dc printenv POSTGRES_USER | tr -d '\r\n')"
DB_NAME="$(dc printenv POSTGRES_DB | tr -d '\r\n')"
[[ -n "$DB_USER" && -n "$DB_NAME" ]] || die "could not read POSTGRES_USER/POSTGRES_DB from the db container"

# A dump is only a backup if it is complete. pg_dump writes this trailer last, so
# its presence rules out the truncation you get from a full disk or a container
# that died mid-dump — the failure that otherwise stays invisible until a restore.
verify() {
    local archive="$1" tail_text n
    [[ -f "$archive" ]] || die "no such file: $archive"
    gzip -t "$archive" 2>/dev/null || die "corrupt gzip: $archive"
    # tail consumes all of zcat's output, so no SIGPIPE race under pipefail.
    tail_text="$(zcat "$archive" | tail -5)"
    grep -q 'PostgreSQL database dump complete' <<<"$tail_text" \
        || die "truncated dump (no completion marker): $archive"
    n="$(zcat "$archive" | grep -c '^CREATE TABLE' || true)"
    [[ "${n:-0}" -gt 0 ]] || die "no CREATE TABLE statements in $archive"
    log "verified: $archive (${n} tables, $(du -h "$archive" | cut -f1))"
}

newest() { find "$DEST" -maxdepth 1 -name 'db-*.sql.gz' | sort | tail -1; }

case "$MODE" in
verify)
    verify "$TARGET"
    exit 0
    ;;

restore-test)
    # Proves the dump actually loads, rather than trusting that it parses.
    [[ -n "$TARGET" ]] || TARGET="$(newest)"
    [[ -n "$TARGET" ]] || die "no archives in $DEST to test"
    verify "$TARGET"
    SCRATCH="restoretest_$$"
    log "restoring $TARGET into scratch database ${SCRATCH}"
    dc createdb -U "$DB_USER" "$SCRATCH" || die "could not create scratch database"
    # shellcheck disable=SC2317
    cleanup() { docker compose exec -T db dropdb -U "$DB_USER" --if-exists "$SCRATCH" </dev/null >/dev/null 2>&1 || true; }
    trap cleanup EXIT
    if ! zcat "$TARGET" | docker compose exec -T db psql -v ON_ERROR_STOP=1 -q -U "$DB_USER" -d "$SCRATCH" >/dev/null; then
        die "restore FAILED — this archive would not have saved you"
    fi
    got="$(dc psql -tAq -U "$DB_USER" -d "$SCRATCH" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" | tr -d '[:space:]')"
    want="$(dc psql -tAq -U "$DB_USER" -d "$DB_NAME" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" | tr -d '[:space:]')"
    log "restored tables: ${got}   production tables: ${want}"
    [[ "$got" == "$want" ]] || die "table count mismatch — restore is not faithful"
    users="$(dc psql -tAq -U "$DB_USER" -d "$SCRATCH" -c "SELECT count(*) FROM users_user" | tr -d '[:space:]')"
    log "restore test PASSED (users_user rows: ${users})"
    exit 0
    ;;
esac

# ─── Backup ────────────────────────────────────────────────────────────────────
mkdir -p "$DEST"
chmod 700 "$DEST"
OUT="${DEST}/db-$(date +%F-%H%M).sql.gz"

log "dumping ${DB_NAME}"
umask 077
# pipefail is on, so a pg_dump failure fails the pipeline instead of leaving a
# well-formed gzip wrapped around a truncated dump.
dc pg_dump -U "$DB_USER" "$DB_NAME" | gzip -9 >"${OUT}.tmp"
mv "${OUT}.tmp" "$OUT"
chmod 600 "$OUT"

verify "$OUT"

mapfile -t stale < <(find "$DEST" -maxdepth 1 -name 'db-*.sql.gz' -printf '%f\n' \
    | sort -r | tail -n +$((KEEP + 1)))
if [[ ${#stale[@]} -gt 0 ]]; then
    for f in "${stale[@]}"; do rm -f "${DEST:?}/${f}"; done
    log "rotated out ${#stale[@]} archive(s), keeping ${KEEP}"
fi

log "done — $(find "$DEST" -maxdepth 1 -name 'db-*.sql.gz' | wc -l) database archive(s) in ${DEST}"
