#!/bin/bash

VERSION="1.1.2"

# 1. Rebuild the .app bundle
echo "Step 1: Building .app with PyInstaller..."
pyinstaller --clean --noconfirm AIrewrite.spec

# 2. Rebuild the DMG
echo "Step 2: Creating DMG installer for v$VERSION..."
# Note: create-dmg usage varies, here we try to match the desired output filename if possible
# or at least keep the echo accurate.
create-dmg dist/AIrewrite.app --overwrite

echo "Done! Your new DMG is ready as 'AIrewrite $VERSION.dmg'"

