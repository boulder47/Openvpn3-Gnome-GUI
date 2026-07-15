# Debian packaging

Build from the repository root:

    sudo apt install devscripts debhelper dh-python pybuild-plugin-pyproject python3-all
    ln -s packaging/debian debian   # or copy
    dpkg-buildpackage -us -uc -b

Result: ../openvpn3-gui_0.1.0-1_all.deb

## Troubleshooting: "Unmet build dependencies: python3-all (>= 3.12)"

This means one of two things:

1. **`python3-all` isn't installed.** Fix: `sudo apt install python3-all`.
2. **Your distro's default `python3` is older than 3.12** (e.g. Ubuntu
   22.04 ships 3.10). `python3-all`'s package *version* tracks its own
   packaging revision, not the language version, so pinning
   `python3-all (>= 3.12)` in Build-Depends is unreliable — it can pass or
   fail independent of which Python interpreters are actually available.
   `debian/control` therefore declares the real minimum via
   `X-Python3-Version: >= 3.12` (the field `dh_python3` reads), and leaves
   the `python3-all` Build-Depends unversioned. If `python3 --version`
   on your build host is below 3.12, you must build on Ubuntu 24.04+ (or
   another distro shipping Python 3.12+) — there's no packaging-level
   workaround for a genuinely missing interpreter.

Check what you have before building:

    python3 --version
    apt-cache policy python3-all
