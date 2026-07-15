# User Guide

## First run

On launch you land on the **Dashboard**. If `openvpn3` isn't installed the
System health panel shows "openvpn3 service: Unavailable" — see the
Installation Guide. The sidebar navigates between the eight main pages;
`Ctrl+1…5` jump directly to the most common ones.

## Importing a profile

1. Open **Profiles** (`Ctrl+2`) → **Import**.
2. Either **Browse…** to a local `.ovpn`/`.conf` file, or paste a URL into
   *Import from URL* and press **Fetch**.
3. Give it a name (defaults to the file name) and choose whether it should
   be **Persistent** (survive logout — recommended).

Once imported you can, from each row's `⋮` menu:

- **Rename / Duplicate / Export…** the profile,
- **Edit tags/notes** — free-form tags (searchable, shown as `#tag` in the
  list) and notes,
- **Manage ACL** — toggle *Public access* (any local user may use the
  profile), grant/revoke specific system usernames, and *Lock down* so only
  the owner can read embedded secrets,
- **Remove** it (asks for confirmation; also deletes any saved credentials).

The star toggles a **favorite**; favorites can be sorted first and appear in
the tray quick-connect menu. Search matches name, remote host, tags, and
notes; the dropdown offers four sort orders including *Last used*.

## Connecting

Press the ▶ button on a profile row, or open **Connections** (`Ctrl+3`),
pick a profile, and hit **Connect**. The **connection transcript** shows the
CLI's live output. When the server requests credentials — username,
password, one-time code, or a PKCS#11 PIN — a dialog appears:

- Type the value and press **Submit**.
- Check **Save in GNOME Keyring** to skip the prompt next time. Saved
  secrets are stored via the Secret Service only; nothing is written to
  disk by this application. Remove them by removing the profile, or via
  GNOME's *Passwords and Keys* (Seahorse).

**Disconnect**, **Reconnect**, and the **Auto-reconnect** switch act on the
session for the currently selected profile. The **history** list below the
transcript records every attempt with its outcome.

## Dashboard

While connected, the dashboard shows the profile and server, public IP, VPN
IP, duration, upload/download totals, DNS servers, gateway, protocol,
measured latency, tunnel interface — and a live two-line **bandwidth
graph** (download in accent color, upload in green). The **System health**
group continuously verifies the openvpn3 service, D-Bus, internet
connectivity, and tunnel health.

## Sessions

**Sessions** (`Ctrl+4`) lists every active session (there can be several at
once). Expand a row for PID, interface, owner, restart count, DNS, and
pushed routes; each session has its own **Disconnect** (confirmed) and
**Restart** buttons. The list auto-refreshes every 5 seconds.

## Live Logs

**Live Logs** (`Ctrl+5`) tails the openvpn3 log service in real time and
interleaves the app's own log. Toolbar controls:

- Filter box — plain-text by default; toggle **.*** for regex.
- **Debug mode** — raises openvpn3 log verbosity.
- **Live tail** — pause/resume streaming.
- Export to a file, copy the visible lines, or clear the view.

Severity is color-coded (errors red, warnings orange, notices blue).

## Network

Shows tunnel details (interface, MTU, IPv4/IPv6, routes, byte counters) and
three diagnostics:

- **Public IP checker** — what the internet currently sees.
- **Latency test** — TCP connect time to your VPN gateway.
- **DNS leak test** — compares your system resolvers against the
  VPN-provided DNS and flags mismatches.

## Notifications & tray

Every notification type (connect, disconnect, error, auth request,
reconnect, certificate expiry) can be toggled in **Settings →
Notifications**. Certificates embedded in profiles are checked at startup
and you're warned the configured number of days before expiry.

Closing the window with **Minimize to tray** enabled keeps the app running;
the tray icon shows status and offers quick connect (favorites),
disconnect-all, show window, and quit.

## Automation

In **Settings → Startup and tray**:

- **Connect on login** — installs an autostart entry.
- **Connect on boot** — generates a systemd user unit (see the install guide
  to enable it).
- **Reconnect when network becomes available** / **on resume from
  suspend** — reacts to NetworkManager and logind signals.
- **Scheduled reconnect** — standard 5-field cron expression
  (default `0 4 * * *` = daily at 04:00).

Hook scripts (pre/post connect/disconnect) receive `OVPN3_GUI_HOOK` and
`OVPN3_GUI_PROFILE` environment variables plus any custom ones you define;
every run is logged with stdout/stderr and exit code.

## Backup and restore

**Settings → Backup and restore** exports a `.tar.gz` containing your
settings, profile metadata (tags/favorites/notes/groups), traffic history,
and exported copies of every profile. **Credentials are intentionally not
included.** Restoring re-imports profiles that aren't already present.

## Developer Console

`Ctrl+Shift+D`. Every CLI invocation the app has made — full command,
exit code, duration, stdout, stderr — plus a prompt to run any `openvpn3`
subcommand manually (arguments only, e.g. `sessions-list`; input is
tokenized and executed directly, never through a shell).

## Global search

`Ctrl+F` searches profiles, active sessions, settings entries, and app
commands from anywhere; activating a result jumps to the right page.
