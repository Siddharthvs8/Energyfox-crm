#!/usr/bin/env bash
#
# Build the EnergyFox CRM Android app.
#
#   ./build_apk.sh                              → points at https://crmenergyfox.com
#   ./build_apk.sh http://10.0.2.2:8000         → dev override, for a local Django
#
# Per-ABI APKs are built as well as the universal one: the universal APK works
# on any phone but carries every architecture (~55 MB), while the arm64 one is
# roughly a third of that and covers every handset sold in the last decade.
set -euo pipefail

cd "$(dirname "$0")"

ARGS=(--release)
if [[ $# -gt 0 ]]; then
  ARGS+=("--dart-define=API_BASE=$1")
  echo "Building with API_BASE=$1"
else
  echo "Building against the production server (https://crmenergyfox.com)."
fi

flutter build apk "${ARGS[@]}"
flutter build apk "${ARGS[@]}" --split-per-abi

echo
echo "APKs → $(pwd)/build/app/outputs/flutter-apk/"
ls -lh build/app/outputs/flutter-apk/*.apk | awk '{print "  " $9 "  " $5}'
echo
echo "These are signed with the debug key — fine for sideloading and internal"
echo "testing, not for Play. For a Play release add a signing config to"
echo "android/app/build.gradle.kts and run: flutter build appbundle"
