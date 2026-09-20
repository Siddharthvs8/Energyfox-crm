#!/usr/bin/env bash
#
# Build the installable EnergyFox CRM PWA.
#
#   ./build_pwa.sh                 → served from the site root  (https://crm.example/)
#   ./build_pwa.sh /app/           → served from a sub-path     (https://crm.example/app/)
#
# CanvasKit is bundled rather than pulled from Google's CDN (--no-web-resources-cdn)
# so the app's own service worker can cache every byte it needs to start offline.
set -euo pipefail

BASE_HREF="${1:-/}"

cd "$(dirname "$0")"
flutter build web \
  --release \
  --no-web-resources-cdn \
  --base-href "$BASE_HREF"

echo
echo "Built → $(pwd)/build/web  (base href: $BASE_HREF)"
echo "Copy that directory to your web root, or point nginx at it."
