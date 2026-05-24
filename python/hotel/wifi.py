"""hotel/wifi.py - WiFi scan + connect over wlan0cli.

Pre-existing uci layout on the Hak5 Pineapple Pager (factory defaults):
    wireless.wlan0cli   STA on radio0 (2.4 GHz) - we modify ssid+key here
    wireless.wlan0mon   monitor on radio0
    wireless.wlan0wpa   PineAP capture AP (disabled by default)
    wireless.wlan0mgmt  management AP

The interface naming + convention comes from the Pineapple-Pager firmware.
The wifi_utils.py module in
    https://github.com/pineapple-pager-projects/pineapple_pager_pagerctl_home
documents this layout - we don't vendor the code but use the same uci
keys + iw scan pattern.

This module is intentionally narrow: just scan, connect (open + WPA),
status, wait-for-IP. No hotspot, no PineAP, no captive portal.
"""
from __future__ import annotations

import subprocess
import time

CLIENT_IFACE = "wlan0cli"
SCAN_IFACE   = "wlan0cli"


# ── Low-level helpers ─────────────────────────────────────────────────

def _uci(*args, timeout: float = 5) -> str:
    try:
        r = subprocess.run(["uci"] + list(args), capture_output=True,
                           text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def _uci_set(key: str, value: str) -> None:
    _uci("set", f"{key}={value}")


def _uci_commit(pkg: str = "wireless") -> None:
    _uci("commit", pkg)


def _wifi_reload(timeout: float = 15) -> None:
    try:
        subprocess.run(["wifi", "reload"], capture_output=True, timeout=timeout)
    except Exception:
        pass


# ── Status ────────────────────────────────────────────────────────────

def current_ssid(iface: str = CLIENT_IFACE) -> str:
    """SSID we are actually associated with right now, or ''."""
    try:
        r = subprocess.run(["iw", "dev", iface, "link"],
                           capture_output=True, text=True, timeout=3)
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.lower().startswith("ssid:"):
                return line.split(None, 1)[1].strip()
    except Exception:
        pass
    return ""


def configured_ssid(iface: str = CLIENT_IFACE) -> str:
    raw = _uci("get", f"wireless.{iface}.ssid").strip().strip("'")
    return raw


def get_ipv4(iface: str = CLIENT_IFACE) -> str:
    """Return first IPv4 on iface (e.g. '10.0.0.42'), or ''."""
    try:
        r = subprocess.run(["ip", "-4", "addr", "show", "dev", iface],
                           capture_output=True, text=True, timeout=3)
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("inet "):
                return line.split()[1].split("/")[0]
    except Exception:
        pass
    return ""


def wait_for_ip(iface: str = CLIENT_IFACE, timeout: float = 30) -> str:
    """Block up to `timeout`s waiting for an IPv4 lease on iface.
    Returns the IP or '' on timeout.
    """
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        ip = get_ipv4(iface)
        if ip and not ip.startswith("169.254."):  # link-local = no DHCP yet
            return ip
        time.sleep(0.5)
    return get_ipv4(iface)  # may still be '' or link-local


# ── Scan ──────────────────────────────────────────────────────────────

def scan(iface: str = SCAN_IFACE, timeout: float = 12) -> list[dict]:
    """Run `iw dev <iface> scan` and return a deduped, signal-sorted list.

    Each entry: {ssid, signal_dbm, encryption: 'open'|'wep'|'wpa'|'wpa2'}.
    Hidden SSIDs (empty name) skipped.
    """
    try:
        r = subprocess.run(["iw", "dev", iface, "scan"],
                           capture_output=True, text=True, timeout=timeout)
    except Exception:
        return []
    out: list[dict] = []
    cur: dict | None = None
    for line in r.stdout.splitlines():
        s = line.strip()
        if line.startswith("BSS "):
            if cur and cur.get("ssid"):
                out.append(cur)
            cur = {"ssid": "", "signal_dbm": -100, "encryption": "open"}
        elif cur is None:
            continue
        elif s.startswith("signal:"):
            try:
                cur["signal_dbm"] = int(float(s.split()[1]))
            except Exception:
                pass
        elif s.startswith("SSID:"):
            cur["ssid"] = s.split(":", 1)[1].strip()
        elif "WPA" in s and "version" in s.lower():
            cur["encryption"] = "wpa"
        elif "RSN" in s and "version" in s.lower():
            cur["encryption"] = "wpa2"
        elif s.startswith("capability:") and "Privacy" in s:
            if cur.get("encryption") == "open":
                cur["encryption"] = "wep"
    if cur and cur.get("ssid"):
        out.append(cur)
    # Dedupe by SSID (keep strongest signal)
    by_ssid: dict[str, dict] = {}
    for ap in out:
        prev = by_ssid.get(ap["ssid"])
        if prev is None or ap["signal_dbm"] > prev["signal_dbm"]:
            by_ssid[ap["ssid"]] = ap
    return sorted(by_ssid.values(),
                  key=lambda x: x["signal_dbm"], reverse=True)


# ── Connect ───────────────────────────────────────────────────────────

def connect(ssid: str, password: str | None = None,
            encryption: str = "psk2",
            iface: str = CLIENT_IFACE) -> bool:
    """Configure wlan0cli to join `ssid` and reload wifi.

    Open AP: pass password=None or "".
    WPA: encryption='psk2' (default) or 'psk'.

    Returns True if uci+wifi-reload succeeded. Does NOT verify association
    (use wait_for_ip for that).
    """
    if not ssid:
        return False
    _uci_set(f"wireless.{iface}.ssid", ssid)
    if password:
        _uci_set(f"wireless.{iface}.encryption", encryption)
        _uci_set(f"wireless.{iface}.key", password)
    else:
        _uci_set(f"wireless.{iface}.encryption", "none")
        _uci("delete", f"wireless.{iface}.key")
    _uci_set(f"wireless.{iface}.disabled", "0")
    _uci_commit("wireless")
    _wifi_reload()
    return True


def disconnect(iface: str = CLIENT_IFACE) -> None:
    """Disable the client interface (used on tool exit if user wants
    to drop the hotel connection back to Mudi-cli mode)."""
    _uci_set(f"wireless.{iface}.disabled", "1")
    _uci_commit("wireless")
    _wifi_reload()


# ── Convenience ───────────────────────────────────────────────────────

def is_iface_up(iface: str = CLIENT_IFACE) -> bool:
    try:
        r = subprocess.run(["iw", "dev", iface, "info"],
                           capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False


if __name__ == "__main__":
    import json
    print("current_ssid:", repr(current_ssid()))
    print("configured_ssid:", repr(configured_ssid()))
    print("ipv4:", repr(get_ipv4()))
    print("scan:")
    for ap in scan()[:10]:
        print(f"  {ap['signal_dbm']:4d} dBm  {ap['encryption']:5s}  {ap['ssid']}")
