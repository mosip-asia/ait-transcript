#!/usr/bin/env bash
# Clone Inji Wallet v0.22.1 and apply the AIT changes (wallet/README.md).
#   BUNDLE_ID=com.yourorg.aitwallet TEAM_ID=ABCDE12345 ./wallet/apply.sh [dest-dir]
# BUNDLE_ID and TEAM_ID are your own Apple bundle identifier and Developer Team ID (both required);
# dest-dir defaults to inji-wallet-ait.
set -euo pipefail

: "${BUNDLE_ID:?set BUNDLE_ID to your bundle identifier, e.g. com.yourorg.aitwallet}"
: "${TEAM_ID:?set TEAM_ID to your Apple Developer Team ID, e.g. ABCDE12345}"

HERE="$(cd "$(dirname "$0")" && pwd)"
PATCH="$HERE/ait-wallet-v0.22.1.patch"
UPSTREAM="${UPSTREAM:-https://github.com/inji/inji-wallet.git}"
DEST="${1:-inji-wallet-ait}"
PBXPROJ="$DEST/ios/Inji.xcodeproj/project.pbxproj"

[ ! -e "$DEST" ] || { echo "$DEST already exists" >&2; exit 1; }

git clone --quiet --branch v0.22.1 --depth 1 "$UPSTREAM" "$DEST"
git -C "$DEST" apply --whitespace=nowarn "$PATCH"

# The patch carries placeholders for the signing identity.
sed -i.bak -e "s/com\.example\.aitwallet/$BUNDLE_ID/g" -e "s/XXXXXXXXXX/$TEAM_ID/g" "$PBXPROJ"
rm -f "$PBXPROJ.bak"

echo "Applied to $DEST (bundle id $BUNDLE_ID, team $TEAM_ID)."
echo "Next: cd $DEST && npm install && (cd ios && pod install)   # Node 20, see wallet/README.md"
