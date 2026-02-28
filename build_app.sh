#!/bin/bash
# build_app.sh — Build TigerTerminal.app standalone bundle
# Run on the iMac G5 (or via SSH) from /Users/imac/terminal/
set -e

APP_NAME="TigerTerminal"
BUNDLE="${APP_NAME}.app"
CONTENTS="${BUNDLE}/Contents"
MACOS="${CONTENTS}/MacOS"
RESOURCES="${CONTENTS}/Resources"
TERMINAL="${MACOS}/terminal"
LIB="${MACOS}/lib/python3.13"
BUILD_DIR="/tmp/tigerterminal-build"
DMG_DIR="/tmp/tigerterminal-release"

PYTHON_BIN="/usr/local/bin/python3.13"
PYTHON_LIB="/usr/local/lib/python3.13"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Building ${APP_NAME}.app ==="
echo "Source dir: ${SCRIPT_DIR}"

# Clean previous build
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/${MACOS}"
mkdir -p "${BUILD_DIR}/${RESOURCES}"
mkdir -p "${BUILD_DIR}/${TERMINAL}"
mkdir -p "${BUILD_DIR}/${LIB}"

cd "${BUILD_DIR}"

# ── 1. Compile launcher ──
echo "[1/7] Compiling launcher..."
# Use GCC 4.0.1 (system) — simple C, no C99 features needed
/usr/bin/gcc -O2 -o "${MACOS}/TigerTerm" "${SCRIPT_DIR}/launcher.c"

# ── 2. Copy Python binary ──
echo "[2/7] Copying Python binary..."
cp "${PYTHON_BIN}" "${MACOS}/python3.13"
chmod +x "${MACOS}/python3.13"

# ── 3. Copy Python stdlib (pruned) ──
echo "[3/7] Copying Python stdlib (pruned)..."

# Copy everything first, then prune
cp -R "${PYTHON_LIB}/" "${LIB}/"

# Remove large unnecessary directories
echo "  Pruning test suite..."
rm -rf "${LIB}/test"
echo "  Pruning config dirs..."
rm -rf "${LIB}/config-3.13-darwin"
rm -rf "${LIB}/config-3.13-x86_64-linux-gnu"
echo "  Pruning __pycache__..."
find "${LIB}" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
echo "  Pruning build/dev-only modules..."
# IDLE editor
rm -rf "${LIB}/idlelib"
# pip bootstrapper
rm -rf "${LIB}/ensurepip"
# Interactive REPL
rm -rf "${LIB}/_pyrepl"
# Documentation data
rm -rf "${LIB}/pydoc_data"
# Python 2→3 converter
rm -rf "${LIB}/lib2to3"
# Deprecated build tool
rm -rf "${LIB}/distutils"
# Virtual environments
rm -rf "${LIB}/venv"
# Turtle graphics demo
rm -rf "${LIB}/turtle.py" "${LIB}/turtledemo"
# Easter egg
rm -rf "${LIB}/antigravity.py"
# Wrong-platform support files
rm -rf "${LIB}/_android_support.py"
rm -rf "${LIB}/_ios_support.py"

# Prune .pyc files from lib-dynload (there shouldn't be any, but just in case)
find "${LIB}/lib-dynload" -name '*.pyc' -delete 2>/dev/null || true

LIB_SIZE=$(du -sh "${LIB}" | cut -f1)
echo "  Pruned stdlib size: ${LIB_SIZE}"

# ── 4. Copy terminal app source ──
echo "[4/7] Copying terminal source..."
for f in terminal_app.py screen.py renderer.py vt_parser.py pty_shell.py; do
    cp "${SCRIPT_DIR}/${f}" "${TERMINAL}/${f}"
done

# ── 5. Copy icon ──
echo "[5/7] Copying icon..."
if [ -f "${SCRIPT_DIR}/TigerTerminal.icns" ]; then
    cp "${SCRIPT_DIR}/TigerTerminal.icns" "${RESOURCES}/TigerTerminal.icns"
else
    echo "  WARNING: TigerTerminal.icns not found, skipping icon"
fi

# ── 6. Write Info.plist ──
echo "[6/7] Writing Info.plist..."
cat > "${CONTENTS}/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>TigerTerm</string>
    <key>CFBundleName</key>
    <string>Tiger Terminal</string>
    <key>CFBundleIdentifier</key>
    <string>com.tiger.terminal</string>
    <key>CFBundleVersion</key>
    <string>2.0</string>
    <key>CFBundleShortVersionString</key>
    <string>2.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>TTRM</string>
    <key>CFBundleIconFile</key>
    <string>TigerTerminal</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.4</string>
    <key>NSHighResolutionCapable</key>
    <false/>
</dict>
</plist>
PLIST

# Write PkgInfo
echo -n "APPLTTRM" > "${CONTENTS}/PkgInfo"

# ── 7. Summary ──
echo "[7/7] Build complete!"
echo ""
TOTAL_SIZE=$(du -sh "${BUILD_DIR}/${BUNDLE}" | cut -f1)
echo "Bundle: ${BUILD_DIR}/${BUNDLE}"
echo "Total size: ${TOTAL_SIZE}"
echo ""

# List component sizes
echo "Component sizes:"
du -sh "${MACOS}/TigerTerm" | awk '{print "  Launcher:  "$1}'
du -sh "${MACOS}/python3.13" | awk '{print "  Python:    "$1}'
du -sh "${LIB}" | awk '{print "  Stdlib:    "$1}'
du -sh "${TERMINAL}" | awk '{print "  Terminal:  "$1}'
if [ -f "${RESOURCES}/TigerTerminal.icns" ]; then
    du -sh "${RESOURCES}/TigerTerminal.icns" | awk '{print "  Icon:      "$1}'
fi

# ── Create DMG ──
echo ""
read -p "Create DMG? [y/N] " CREATE_DMG
if [ "${CREATE_DMG}" = "y" ] || [ "${CREATE_DMG}" = "Y" ]; then
    echo "Creating DMG..."
    rm -rf "${DMG_DIR}"
    mkdir -p "${DMG_DIR}"
    cp -R "${BUILD_DIR}/${BUNDLE}" "${DMG_DIR}/"

    DMG_PATH="${SCRIPT_DIR}/${APP_NAME}.dmg"
    rm -f "${DMG_PATH}"
    hdiutil create -volname "Tiger Terminal" -srcfolder "${DMG_DIR}" \
        -format UDZO "${DMG_PATH}"

    DMG_SIZE=$(du -sh "${DMG_PATH}" | cut -f1)
    echo "DMG created: ${DMG_PATH} (${DMG_SIZE})"
fi

# ── Install to /Applications ──
echo ""
read -p "Install to /Applications? [y/N] " DO_INSTALL
if [ "${DO_INSTALL}" = "y" ] || [ "${DO_INSTALL}" = "Y" ]; then
    echo "Installing..."
    rm -rf "/Applications/${BUNDLE}"
    cp -R "${BUILD_DIR}/${BUNDLE}" "/Applications/${BUNDLE}"

    # Refresh Finder's icon cache so the icon shows immediately
    rm -f /Library/Caches/com.apple.LaunchServices-*.csstore 2>/dev/null
    rm -f ~/Library/Caches/com.apple.LaunchServices-*.csstore 2>/dev/null
    LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"
    if [ -x "${LSREGISTER}" ]; then
        "${LSREGISTER}" -f "/Applications/${BUNDLE}" 2>/dev/null
    fi
    killall Finder 2>/dev/null

    echo "Installed to /Applications/${BUNDLE}"
fi

echo ""
echo "=== Done ==="
