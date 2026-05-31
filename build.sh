#!/bin/bash
set -euo pipefail

APP_NAME="Metronome"
BUNDLE="dist/${APP_NAME}.app"
CONTENTS="${BUNDLE}/Contents"
MACOS="${CONTENTS}/MacOS"
RESOURCES="${CONTENTS}/Resources"
PYTHON=$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3)
if [[ "$PYTHON" == "/usr/bin/python3" ]]; then
  echo "ERROR: Only macOS system Python found. Install Python 3.10+ via Homebrew:" >&2
  echo "  brew install python@3.13" >&2
  exit 1
fi

echo "Building ${BUNDLE} with ${PYTHON}..."

rm -rf "${BUNDLE}"
mkdir -p "${MACOS}" "${RESOURCES}/lib" "${RESOURCES}/lib/site-packages"

# Info.plist
cat > "${CONTENTS}/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Metronome</string>
    <key>CFBundleDisplayName</key>
    <string>Metronome</string>
    <key>CFBundleIdentifier</key>
    <string>com.local.metronome</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>Metronome</string>
    <key>CFBundleIconFile</key>
    <string>Metronome</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © 2026</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
EOF

# Launcher script
cat > "${MACOS}/${APP_NAME}" << EOF
#!/bin/bash
DIR="\$(cd "\$(dirname "\$0")" && pwd)"
RESOURCES="\$(cd "\$DIR/../Resources" && pwd)"
export PYTHONPATH="\$RESOURCES/lib:\$RESOURCES/lib/site-packages"
exec ${PYTHON} -c "
import sys
sys.path.insert(0, '\$RESOURCES/lib')
from metronome.app import main
main()
"
EOF
chmod +x "${MACOS}/${APP_NAME}"

# Source files
cp -r metronome "${RESOURCES}/lib/metronome"
cp -r ui        "${RESOURCES}/ui"
cp icons/Metronome.icns "${RESOURCES}/Metronome.icns"

# Dependencies
"${PYTHON}" -m pip install -q --target "${RESOURCES}/lib/site-packages" -r requirements.txt

echo "Done: ${BUNDLE}"
