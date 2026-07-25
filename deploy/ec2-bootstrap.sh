#!/usr/bin/env bash
# EnergyFox CRM — EC2 bootstrap / redeploy (Docker Compose, single instance).
#
#   sudo ./deploy/ec2-bootstrap.sh <public-host>
#
# <public-host> is the EC2 public IPv4 (or domain) users hit in the browser.
# Safe to re-run: env files are created once (secrets are generated and then
# preserved), while the host-dependent keys are refreshed every run — so an IP
# change is just another run of this script.
set -euo pipefail

HOST="${1:-}"
if [[ -z "$HOST" ]]; then
    echo "usage: sudo $0 <public-ip-or-domain>" >&2
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log() { echo -e "\n\033[1;32m==>\033[0m $*"; }

rand() { head -c 256 /dev/urandom | tr -dc 'A-Za-z0-9' | head -c "$1"; }

# Set KEY=VALUE in an env file, replacing any existing line for that key.
set_env() {
    local file="$1" key="$2" val="$3"
    if grep -q "^${key}=" "$file" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${val}|" "$file"
    else
        printf '%s=%s\n' "$key" "$val" >>"$file"
    fi
}

# ─── 1. Docker ─────────────────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    log "Installing Docker Engine + Compose plugin"
    apt-get update -y
    apt-get install -y ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg |
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        >/etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    usermod -aG docker ubuntu || true
    systemctl enable --now docker
else
    log "Docker already installed — $(docker --version)"
fi

# ─── 2. Swap ───────────────────────────────────────────────────────────────────
# The Next.js production build is the memory peak here; 4 GB of RAM without swap
# is where it gets OOM-killed on a t3.medium.
if ! swapon --show | grep -q '/swapfile'; then
    log "Adding 2G swapfile (headroom for the Next.js build)"
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
fi

# ─── 3. Environment files ──────────────────────────────────────────────────────
# Both are gitignored, so they are generated here rather than pulled.
if [[ ! -f .env ]]; then
    log "Creating .env (compose: database + frontend build args)"
    cat >.env <<EOF
DB_NAME=energyfox_crm
DB_USER=energyfox
DB_PASSWORD=$(rand 32)

# Blank API base ⇒ the browser calls the current origin and nginx proxies /api
# to Django. This is what keeps an IP change from needing a frontend rebuild.
NEXT_PUBLIC_API_PROTOCOL=http
NEXT_PUBLIC_API_PORT=
NEXT_PUBLIC_API_BASE=
EOF
fi

# shellcheck disable=SC1091
set -a && . ./.env && set +a

if [[ ! -f backend/.env ]]; then
    log "Creating backend/.env (Django)"
    cat >backend/.env <<EOF
# --- DJANGO ---
SECRET_KEY=$(rand 50)
DEBUG=False
SECURE_COOKIES=False

# --- DATABASE (DB_HOST is set to the 'db' service by docker-compose) ---
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
DB_PORT=5432

# --- TELEPHONY / AI / PAYMENTS (fill in as needed) ---
AIRTEL_CUSTOMER_ID=
AIRTEL_AUTH_KEY=
AIRTEL_PHONE_NUMBER=
AIRTEL_API_BASE_URL=https://iq.airtel.in
GEMINI_API_KEY=
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
EOF
fi

# Webroot + cert storage for deploy/enable-tls.sh. Created here so Docker does
# not create them root-owned on first `up`, which is what breaks compose for the
# ubuntu user.
mkdir -p certbot/conf certbot/www

# TLS is on only if this host actually has a certificate. Checking for it keeps
# a re-run (say, after an IP change) from quietly reverting an https deployment
# back to http — every scheme-dependent key below is rewritten every run.
if [[ -f "certbot/conf/live/${HOST}/fullchain.pem" ]]; then
    SCHEME="https"
    NGINX_CONF="./nginx-tls.conf"
    SECURE_COOKIES="True"
else
    SCHEME="http"
    NGINX_CONF="./nginx.conf"
    # Over plain HTTP the browser withholds Secure cookies and admin login
    # silently bounces back to the login page.
    SECURE_COOKIES="False"
fi

log "Pointing the stack at ${SCHEME}://${HOST}"
# Scheme-dependent, so refreshed every run even if .env was written by hand —
# an https here against a plain-HTTP host sends every API call to a dead URL.
set_env .env NGINX_CONF "$NGINX_CONF"
set_env .env NEXT_PUBLIC_API_PROTOCOL "$SCHEME"
set_env .env NEXT_PUBLIC_API_BASE ""
set_env .env NEXT_PUBLIC_API_PORT ""
set_env backend/.env ALLOWED_HOSTS "${HOST},localhost,127.0.0.1"
set_env backend/.env CSRF_TRUSTED_ORIGINS "${SCHEME}://${HOST}"
set_env backend/.env CORS_ALLOWED_ORIGINS "${SCHEME}://${HOST}"
set_env backend/.env AIRTEL_BRIDGE_BASE_URL "${SCHEME}://${HOST}"
set_env backend/.env SECURE_COOKIES "$SECURE_COOKIES"
# This script runs as root, so hand the generated files back to whoever owns the
# checkout — otherwise `docker compose` as that user can't read .env.
chown "$(stat -c '%U:%G' "$REPO_ROOT")" .env backend/.env
chown "$(stat -c '%U:%G' "$REPO_ROOT")" certbot certbot/conf certbot/www
chmod 600 .env backend/.env

# ─── 4. Build & start ──────────────────────────────────────────────────────────
log "Building images (first run takes a few minutes)"
docker compose build

log "Starting the stack"
docker compose up -d

log "Waiting for the backend to become healthy"
for _ in $(seq 1 60); do
    status="$(docker compose ps --format '{{.Service}} {{.Health}}' 2>/dev/null | awk '$1=="backend"{print $2}')"
    [[ "$status" == "healthy" ]] && break
    sleep 5
done

docker compose ps
log "Done — ${SCHEME}://${HOST}"
echo "Create the first admin user with:"
echo "  cd ${REPO_ROOT} && docker compose exec backend python manage.py createsuperuser"
if [[ "$SCHEME" == "http" ]]; then
    echo
    echo "Serving plain HTTP. To put this on a domain with TLS:"
    echo "  sudo ./deploy/enable-tls.sh <domain> <email>"
fi
