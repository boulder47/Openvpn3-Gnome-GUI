#!/usr/bin/env bash
# Builds an AppImage using python-appimage-style bundling on Ubuntu 24.04.
# Requires: wget, fuse, and the appimagetool.
set -euo pipefail

APP=openvpn3-gui
VERSION=0.1.0
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD="$ROOT/build/appimage"
APPDIR="$BUILD/$APP.AppDir"

rm -rf "$BUILD"
mkdir -p "$APPDIR/usr"

# 1. Install the app + python deps into the AppDir prefix.
python3 -m pip install --prefix="$APPDIR/usr" "$ROOT"

# 2. System libraries: GTK4/Libadwaita are large; the pragmatic AppImage
#    approach for GNOME apps is to rely on the host's GTK stack (present on
#    any Ubuntu 24.04+/GNOME 46+ system) and only bundle the Python level.
mkdir -p "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp "$ROOT/data/org.openvpn3.Gui.desktop" "$APPDIR/"
cp "$ROOT/data/org.openvpn3.Gui.desktop" "$APPDIR/usr/share/applications/"
cp "$ROOT/data/icons/hicolor/scalable/apps/org.openvpn3.Gui.svg" "$APPDIR/org.openvpn3.Gui.svg"
cp "$ROOT/data/icons/hicolor/scalable/apps/org.openvpn3.Gui.svg" \
   "$APPDIR/usr/share/icons/hicolor/scalable/apps/"

# 3. AppRun
cat > "$APPDIR/AppRun" << 'RUN'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "$0")")"
PYVER="$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
export PYTHONPATH="$HERE/usr/lib/python$PYVER/site-packages:$HERE/usr/lib/python3/dist-packages:$PYTHONPATH"
export PATH="$HERE/usr/bin:$PATH"
exec python3 -m openvpn3_gui.main "$@"
RUN
chmod +x "$APPDIR/AppRun"

# 4. Pack
if ! command -v appimagetool >/dev/null; then
  wget -q https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage \
    -O "$BUILD/appimagetool" && chmod +x "$BUILD/appimagetool"
  APPIMAGETOOL="$BUILD/appimagetool"
else
  APPIMAGETOOL=appimagetool
fi
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$BUILD/${APP}-${VERSION}-x86_64.AppImage"
echo "Built: $BUILD/${APP}-${VERSION}-x86_64.AppImage"
