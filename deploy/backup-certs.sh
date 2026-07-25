#!/usr/bin/env bash
# EnergyFox CRM — snapshot the Let's Encrypt state to a rotated local archive.
#
#   sudo ./deploy/backup-certs.sh [--dest DIR] [--keep N] [--verify-only FILE]
#
# Certificates live on the instance disk in ./certbot/conf (not a Docker volume),
# so `docker compose down -v` or a lost checkout takes them with it. Re-issuing is
# usually easy, but Let's Encrypt allows only 5 certificates per domain per week —
# so if you are already mid-incident, re-issuing may not be available to you.
#
# What is captured: the certificates, their private keys, the ACME account key,
# and the renewal config. That is everything needed to restore without contacting
# Let's Encrypt at all.
#
# NOTE: this backs up certificates ONLY. The database is not included — see
# EC2_DOCKER_DEPLOY.md for the pg_dump command.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DEST="/var/backups/energyfox"
KEEP=30
VERIFY_ONLY=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dest)        DEST="$2"; shift 2 ;;
        --keep)        KEEP="$2"; shift 2 ;;
        --verify-only) VERIFY_ONLY="$2"; shift 2 ;;
        *) echo "usage: sudo $0 [--dest DIR] [--keep N] [--verify-only FILE]" >&2; exit 1 ;;
    esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] error: $*" >&2; exit 1; }

# An archive is only a backup if it restores. Both the writer and --verify-only
# use this, so the check is identical to what a restore would rely on.
verify() {
    local archive="$1" listing n
    # Listed once into a variable rather than piped into grep. `tar | grep -q`
    # is a race under `set -o pipefail`: grep -q exits on the first match and
    # closes the pipe, tar takes SIGPIPE, and pipefail turns that into a failed
    # verification — intermittently, depending on which finishes first.
    listing="$(tar -tzf "$archive" 2>/dev/null)" || die "archive is not readable: $archive"
    # The private key is the part that cannot be regenerated from anything else.
    n="$(grep -c 'archive/.*/privkey.*\.pem' <<<"$listing" || true)"
    [[ "${n:-0}" -gt 0 ]] \
        || die "no private key inside $archive — refusing to call this a backup"
    log "verified: $archive ($n private key(s), $(du -h "$archive" | cut -f1))"
}

if [[ -n "$VERIFY_ONLY" ]]; then
    [[ -f "$VERIFY_ONLY" ]] || die "no such file: $VERIFY_ONLY"
    verify "$VERIFY_ONLY"
    exit 0
fi

SRC="${REPO_ROOT}/certbot/conf"
[[ -d "$SRC" ]] || die "no certificates at ${SRC} — nothing to back up (is TLS enabled?)"

# 0700/0600: these archives contain private keys in the clear.
mkdir -p "$DEST"
chmod 700 "$DEST"

OUT="${DEST}/certbot-$(date +%F-%H%M).tar.gz"

# No -h/--dereference: live/ holds symlinks into archive/, and both are inside
# the tree being captured. Storing them as symlinks keeps the layout certbot
# expects; dereferencing would silently turn them into duplicate regular files
# and break the next renewal after a restore.
log "backing up ${SRC}"
umask 077
tar -czf "${OUT}.tmp" -C "$REPO_ROOT" certbot/conf
mv "${OUT}.tmp" "$OUT"
chmod 600 "$OUT"

verify "$OUT"

# Rotation. Keeps the newest $KEEP, by filename — the timestamp format sorts
# lexicographically, so this stays correct regardless of mtime changes.
mapfile -t stale < <(find "$DEST" -maxdepth 1 -name 'certbot-*.tar.gz' -printf '%f\n' \
    | sort -r | tail -n +$((KEEP + 1)))
if [[ ${#stale[@]} -gt 0 ]]; then
    for f in "${stale[@]}"; do rm -f "${DEST}/${f}"; done
    log "rotated out ${#stale[@]} archive(s), keeping ${KEEP}"
fi

log "done — $(find "$DEST" -maxdepth 1 -name 'certbot-*.tar.gz' | wc -l) archive(s) in ${DEST}"
