# Installation Guide

OpenVPN3 GUI targets **Ubuntu 24.04+** (and any distribution with GNOME 46+,
GTK 4.12+, Libadwaita 1.5+, Python 3.12+).

## 0. Prerequisite: openvpn3-linux

The GUI is a frontend; the tunnels are created by openvpn3-linux's D-Bus
system services. Install them first:

```bash
# Ubuntu 24.04+ (universe) or via OpenVPN's official repository:
sudo apt update
sudo apt install openvpn3
# Verify:
openvpn3 version
```

If your distribution doesn't package it, follow
<https://openvpn.net/openvpn3-linux/> — the official apt repository covers
Ubuntu LTS releases.

## 1. Debian package (recommended on Ubuntu)

```bash
sudo apt install devscripts debhelper dh-python pybuild-plugin-pyproject
git clone https://github.com/example/openvpn3-gui && cd openvpn3-gui
cp -r packaging/debian debian
dpkg-buildpackage -us -uc -b
sudo apt install ../openvpn3-gui_0.1.0-1_all.deb
```

Runtime dependencies (pulled automatically): `python3-gi`, `gir1.2-gtk-4.0`,
`gir1.2-adw-1`, `gir1.2-secret-1`, `python3-cryptography`, `openvpn3`.
Recommended for the tray icon: `gir1.2-ayatanaappindicator3-0.1` and the
`gnome-shell-extension-appindicator` extension (preinstalled on Ubuntu).

## 2. Flatpak

```bash
flatpak install org.gnome.Platform//46 org.gnome.Sdk//46
cd packaging/flatpak
flatpak-builder --user --install --force-clean build-dir org.openvpn3.Gui.json
```

Because the `openvpn3` CLI must run on the **host** (it talks to system
D-Bus services that manage kernel tunnels), grant the sandbox host-spawn
access and point the app at the host binary:

```bash
flatpak override --user --talk-name=org.freedesktop.Flatpak org.openvpn3.Gui
```

Then in **Settings → Advanced → CLI path** enter:

```
flatpak-spawn --host openvpn3
```

## 3. AppImage

```bash
./packaging/appimage/build-appimage.sh
./build/appimage/openvpn3-gui-0.1.0-x86_64.AppImage
```

The AppImage bundles the Python layer and relies on the host's GTK4 stack
(present on any Ubuntu 24.04+/GNOME system) and host `openvpn3`.

## 4. From source (development)

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-secret-1 \
                 python3-cryptography openvpn3
git clone https://github.com/example/openvpn3-gui && cd openvpn3-gui
python3 -m venv --system-site-packages .venv && source .venv/bin/activate
pip install -e ".[dev]"
openvpn3-gui --debug
```

`--system-site-packages` is required so the venv can see the distro's
PyGObject/GTK bindings (they are not pip-installable without compiling).

## 5. Optional: connect on boot

The Settings → Startup "Connect on boot" toggle generates
`~/.config/systemd/user/openvpn3-gui-autoconnect.service`. Enable it and
allow your user services to start at boot:

```bash
systemctl --user enable openvpn3-gui-autoconnect.service
loginctl enable-linger "$USER"
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| "openvpn3 executable was not found" | Install openvpn3-linux, or set the path in Settings → Advanced |
| No tray icon on GNOME | Enable the AppIndicator Shell extension (`gnome-shell-extension-appindicator`) |
| "Secret Service is not available" | Ensure `gnome-keyring` is running; credentials simply won't be saved otherwise |
| D-Bus health shows Unavailable | `sudo systemctl status openvpn3-session@*.service`; reinstall openvpn3-linux |
