# Flatpak packaging

Note: the `openvpn3` CLI and its D-Bus system services must be installed on
the *host* (they manage kernel tunnels and cannot live inside the sandbox).
The manifest grants the sandbox system-bus talk access to the
`net.openvpn.v3.*` names. Since the Flatpak cannot exec the host binary
directly, the recommended host bridge is:

    flatpak override --user --talk-name=org.freedesktop.Flatpak org.openvpn3.Gui

and setting the CLI path in Settings → Advanced to:

    flatpak-spawn --host openvpn3

Build:

    flatpak-builder --user --install --force-clean build-dir org.openvpn3.Gui.json
