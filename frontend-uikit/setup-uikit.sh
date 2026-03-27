#!/bin/bash
# Clone UIkit from GitHub and copy built assets to vendor/uikit.
# Run once to use local UIkit instead of CDN.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR="$SCRIPT_DIR/vendor/uikit"
TMP="$SCRIPT_DIR/.uikit-tmp"

echo "Cloning UIkit..."
rm -rf "$TMP"
# Use SSH (git@github.com) or HTTPS: https://github.com/uikit/uikit.git
git clone --depth 1 git@github.com:uikit/uikit.git "$TMP"

echo "Building UIkit..."
cd "$TMP"
npm install
npm run build

echo "Copying dist to vendor/uikit..."
mkdir -p "$VENDOR"
cp -r dist/css "$VENDOR/"
cp -r dist/js "$VENDOR/"

echo "Cleaning up..."
cd "$SCRIPT_DIR"
rm -rf "$TMP"

echo "Done. UIkit is now at $VENDOR"
