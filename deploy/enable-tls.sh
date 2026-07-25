#!/usr/bin/env bash
# EnergyFox CRM — switch the stack from plain HTTP to a domain + Let's Encrypt TLS.
#
#   sudo ./deploy/enable-tls.sh <domain> <email> [extra-domain ...] [--staging] [--force]
#
# e.g.  sudo ./deploy/enable-tls.sh crm.energyfox.in admin@energyfox.in
#       sudo ./deploy/enable-tls.sh energyfox.in admin@energyfox.in www.energyfox.in
#
# Prerequisites, both of which have to be done outside this box:
#   1. An A record for each domain pointing at this instance's public IP.
#   2. Inbound TCP 443 open in the security group (80 is already open).
#
# Safe to re-run. It always issues against the plain-HTTP config first, so a
# half-finished previous run (TLS config selected, certificate missing — which
# leaves nginx unable to start) repairs itself rather than wedging.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log()  { echo -e "\n\033[1;32m==>\033[0m $*"; }
warn() { echo -e "\033[1;33mwarning:\033[0m $*" >&2; }
die()  { echo -e "\033[1;31merror:\033[0m $*" >&2; exit 1; }

# ─── Arguments ─────────────────────────────────────────────────────────────────
DOMAINS=()
EMAIL=""
STAGING=0
FORCE=0

for arg in "$@"; do
    case "$arg" in
        --staging) STAGING=1 ;;
        --force)   FORCE=1 ;;
        -*)        die "unknown flag: $arg" ;;
        *@*)       EMAIL="$arg" ;;
        *)         DOMAINS+=("$arg") ;;
    esac
done

[[ ${#DOMAINS[@]} -gt 0 ]] || die "usage: sudo $0 <domain> <email> [extra-domain ...] [--staging] [--force]"
[[ -n "$EMAIL" ]] || die "an email address is required — Let's Encrypt uses it for expiry warnings"

PRIMARY="${DOMAINS[0]}"
SERVER_NAMES="${DOMAINS[*]}"
CERT_ARGS=()
for d in "${DOMAINS[@]}"; do CERT_ARGS+=(-d "$d"); done

# Set KEY=VALUE in an env file, replacing any existing line for that key.
set_env() {
    local file="$1" key="$2" val="$3"
    if grep -q "^${key}=" "$file" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${val}|" "$file"
    else
        printf '%s=%s\n' "$key" "$val" >>"$file"
    fi
}

[[ -f .env && -f backend/.env ]] || die "no .env / backend/.env — run deploy/ec2-bootstrap.sh first"

# ─── 1. Preflight: does DNS actually point here? ───────────────────────────────
# Getting this wrong burns a Let's Encrypt rate limit slot (5 failed validations
# per hour), so check before asking them for a certificate.
log "Checking DNS for: ${SERVER_NAMES}"

TOKEN="$(curl -sf -X PUT 'http://169.254.169.254/latest/api/token' \
    -H 'X-aws-ec2-metadata-token-ttl-seconds: 300' 2>/dev/null || true)"
PUBLIC_IP="$(curl -sf -H "X-aws-ec2-metadata-token: ${TOKEN}" \
    http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"
[[ -n "$PUBLIC_IP" ]] || PUBLIC_IP="$(curl -sf https://api.ipify.org 2>/dev/null || true)"
[[ -n "$PUBLIC_IP" ]] || warn "could not determine this instance's public IP"

dns_ok=1
for d in "${DOMAINS[@]}"; do
    resolved="$(getent ahostsv4 "$d" 2>/dev/null | awk '{print $1}' | sort -u | tr '\n' ' ' | sed 's/ $//')"
    if [[ -z "$resolved" ]]; then
        warn "${d} does not resolve yet"
        dns_ok=0
    elif [[ -n "$PUBLIC_IP" && " $resolved " != *" $PUBLIC_IP "* ]]; then
        warn "${d} resolves to ${resolved}, not ${PUBLIC_IP}"
        dns_ok=0
    else
        echo "    ${d} -> ${resolved}"
    fi
done

if [[ $dns_ok -eq 0 ]]; then
    if [[ $FORCE -eq 1 ]]; then
        warn "continuing anyway (--force)"
    else
        die "DNS is not pointing at this instance yet. Add an A record for each
       domain -> ${PUBLIC_IP:-the public IP of this instance}, wait for the TTL
       to expire, then re-run. Override with --force if you know DNS is fine."
    fi
fi

# ─── 2. Webroot for the ACME challenge ─────────────────────────────────────────
# Created here rather than left to Docker: a bind-mount source that does not
# exist is created root-owned, and root-owned files in this checkout are what
# break `docker compose` for the ubuntu user.
log "Preparing certbot directories"
mkdir -p certbot/conf certbot/www
# Only the directories — certbot's own files under conf/ (account key, private
# keys) are root-owned by the container and should stay that way.
chown "$(stat -c '%U:%G' "$REPO_ROOT")" certbot certbot/conf certbot/www

# ─── 3. Serve the challenge over plain HTTP ────────────────────────────────────
# The TLS config cannot load without a certificate, so issuance always happens
# on the HTTP config regardless of what the stack was running before.
log "Bringing nginx up on the plain-HTTP config to serve the challenge"
set_env .env NGINX_CONF "./nginx.conf"
docker compose up -d nginx
sleep 3

# ─── 4. Issue the certificate ──────────────────────────────────────────────────
log "Requesting a certificate for ${SERVER_NAMES}"
staging_arg=()
if [[ $STAGING -eq 1 ]]; then
    staging_arg=(--staging)
    warn "using the Let's Encrypt STAGING environment — browsers will not trust this certificate"
fi

# --non-interactive matters: certbot prompts when the domain list of an existing
# lineage changes, and a prompt here would hang the deploy. --expand answers that
# case (adding www to an existing cert); --keep-until-expiring makes a re-run with
# an unchanged, still-valid certificate a no-op instead of burning a rate limit.
docker compose run --rm --entrypoint certbot certbot \
    certonly --webroot -w /var/www/certbot \
    "${CERT_ARGS[@]}" \
    --email "$EMAIL" \
    --agree-tos --no-eff-email \
    --non-interactive --expand --keep-until-expiring \
    "${staging_arg[@]}" \
    || die "certbot failed — see the output above. Common causes: port 80 blocked
       from the internet, DNS not propagated, or a rate limit from repeated tries."

[[ -f "certbot/conf/live/${PRIMARY}/fullchain.pem" ]] \
    || die "certbot reported success but certbot/conf/live/${PRIMARY}/fullchain.pem is missing"

# ─── 5. Generate the TLS nginx config ──────────────────────────────────────────
log "Writing nginx-tls.conf"
sed -e "s|__SERVER_NAMES__|${SERVER_NAMES}|g" \
    -e "s|__DOMAIN__|${PRIMARY}|g" \
    nginx-tls.conf.template >nginx-tls.conf
chown "$(stat -c '%U:%G' "$REPO_ROOT")" nginx-tls.conf

# ─── 6. Point the application at https ─────────────────────────────────────────
# NEXT_PUBLIC_API_PROTOCOL is read at build time by next.config.ts and baked
# into the client bundle, so this needs the frontend rebuild in step 7.
log "Switching the stack to https://${PRIMARY}"
set_env .env NGINX_CONF "./nginx-tls.conf"
set_env .env NEXT_PUBLIC_API_PROTOCOL "https"
set_env .env NEXT_PUBLIC_API_BASE ""
set_env .env NEXT_PUBLIC_API_PORT ""

hosts="$(IFS=,; echo "${DOMAINS[*]}")"
origins="$(printf 'https://%s,' "${DOMAINS[@]}")"; origins="${origins%,}"
set_env backend/.env ALLOWED_HOSTS "${hosts},${PUBLIC_IP:-127.0.0.1},localhost,127.0.0.1"
set_env backend/.env CSRF_TRUSTED_ORIGINS "$origins"
set_env backend/.env CORS_ALLOWED_ORIGINS "$origins"
set_env backend/.env AIRTEL_BRIDGE_BASE_URL "https://${PRIMARY}"
# Back to Secure-only session/CSRF cookies now that there is TLS to carry them.
# This also re-enables HSTS in settings.py. SECURE_SSL_REDIRECT stays off —
# nginx already does the redirect, and turning it on would 301 the :80 health check.
set_env backend/.env SECURE_COOKIES "True"

chown "$(stat -c '%U:%G' "$REPO_ROOT")" .env backend/.env
chmod 600 .env backend/.env

# ─── 7. Rebuild and restart ────────────────────────────────────────────────────
log "Rebuilding the frontend with the https API protocol"
docker compose up -d --build

log "Waiting for the backend to become healthy"
for _ in $(seq 1 60); do
    status="$(docker compose ps --format '{{.Service}} {{.Health}}' 2>/dev/null | awk '$1=="backend"{print $2}')"
    [[ "$status" == "healthy" ]] && break
    sleep 5
done
docker compose ps

# ─── 8. Verify from the outside ────────────────────────────────────────────────
log "Verifying"
fail=0
check() {
    local desc="$1" expected="$2" got="$3"
    if [[ "$got" == "$expected" ]]; then
        printf '    \033[1;32mok\033[0m   %-38s %s\n' "$desc" "$got"
    else
        printf '    \033[1;31mFAIL\033[0m %-38s got %s, expected %s\n' "$desc" "$got" "$expected"
        fail=1
    fi
}

sleep 5
check "https://${PRIMARY}/health" "200" \
    "$(curl -s -o /dev/null -w '%{http_code}' "https://${PRIMARY}/health" || echo 000)"
check "https://${PRIMARY}/ (frontend)" "200" \
    "$(curl -s -o /dev/null -w '%{http_code}' "https://${PRIMARY}/" || echo 000)"
check "http://${PRIMARY}/ redirects" "301" \
    "$(curl -s -o /dev/null -w '%{http_code}' "http://${PRIMARY}/" || echo 000)"
# A 500 here means the DB or JWT wiring is broken, not the credentials.
check "POST /api/token/ (bad creds -> 401)" "401" \
    "$(curl -s -o /dev/null -w '%{http_code}' -X POST "https://${PRIMARY}/api/token/" \
        -H 'Content-Type: application/json' -d '{"username":"x","password":"y"}' || echo 000)"

expiry="$(docker compose run --rm --entrypoint openssl certbot \
    x509 -enddate -noout -in "/etc/letsencrypt/live/${PRIMARY}/fullchain.pem" 2>/dev/null | cut -d= -f2 || true)"
if [[ -n "$expiry" ]]; then
    echo "    certificate expires: ${expiry}"
fi

if [[ $fail -ne 0 ]]; then
    warn "some checks failed — inspect with: docker compose logs nginx backend"
    exit 1
fi

log "Done — https://${PRIMARY}"
echo "Renewal runs twice a day in the certbot container; nginx reloads every 6h to pick it up."
if [[ $STAGING -eq 1 ]]; then
    warn "this is a STAGING certificate — re-run without --staging for a trusted one"
fi
