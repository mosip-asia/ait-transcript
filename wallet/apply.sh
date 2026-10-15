#!/usr/bin/env bash
# Clone Inji Wallet v0.22.1 and apply the AIT changes for one platform (wallet/README.md).
#   BUNDLE_ID=com.yourorg.aitwallet TEAM_ID=ABCDE12345 ./wallet/apply.sh ios [dest-dir]
# ios needs your own Apple bundle identifier and Developer Team ID (both required).
# dest-dir defaults to inji-wallet-ait. Platforms: ios (android: not yet, see wallet/README.md).
set -euo pipefail

PLATFORM="${1:-}"
DEST="${2:-inji-wallet-ait}"
HERE="$(cd "$(dirname "$0")" && pwd)"
UPSTREAM="${UPSTREAM:-https://github.com/inji/inji-wallet.git}"

case "$PLATFORM" in
  ios)
    : "${BUNDLE_ID:?set BUNDLE_ID to your bundle identifier, e.g. com.yourorg.aitwallet}"
    : "${TEAM_ID:?set TEAM_ID to your Apple Developer Team ID, e.g. ABCDE12345}"
    ;;
  android)
    echo "android: no Android patch yet. Apply wallet/common/ait-common.patch yourself and set your own application id and signing; see wallet/README.md." >&2
    exit 2
    ;;
  *)
    echo "usage: [BUNDLE_ID=... TEAM_ID=...] $0 ios [dest-dir]" >&2
    exit 2
    ;;
esac

[ ! -e "$DEST" ] || { echo "$DEST already exists" >&2; exit 1; }

git clone --quiet --branch v0.22.1 --depth 1 "$UPSTREAM" "$DEST"
git -C "$DEST" apply --whitespace=nowarn "$HERE/common/ait-common.patch" "$HERE/$PLATFORM/ait-$PLATFORM.patch"

if [ "$PLATFORM" = ios ]; then
  # The iOS patch carries placeholders for the signing identity.
  PBXPROJ="$DEST/ios/Inji.xcodeproj/project.pbxproj"
  sed -i.bak -e "s/com\.example\.aitwallet/$BUNDLE_ID/g" -e "s/XXXXXXXXXX/$TEAM_ID/g" "$PBXPROJ"
  rm -f "$PBXPROJ.bak"
  echo "Applied common + ios to $DEST (bundle id $BUNDLE_ID, team $TEAM_ID)."
  echo "Next: cd $DEST && npm install && (cd ios && pod install)   # Node 20, see wallet/ios/README.md"
fi
