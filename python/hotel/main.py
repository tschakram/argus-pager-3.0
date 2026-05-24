#!/usr/bin/env python3
"""argus-hotel - Pager-native DHCP-Fingerprint capture for Hotel/Cafe-Mode.

Entry point invoked by payload.sh. Runs entirely on the pager - no SSH,
no Laptop. Designed so the operator's personal devices never need to
join the (potentially-hostile) hotel WiFi.

Flow:
  splash -> mode_picker -> [scan + AP-pick + connect] -> capture-with-
  live-counter -> mini-report -> back to mode_picker

Capture writes manual_<ts>_dhcp.pcap into /root/loot/argus/pcap, which
the next regular Argus session auto-includes via external_intel's
manual-pcap glob (Fingerbank enrichment happens there, not here).
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

# pagerctl bootstrap (matches argus-finder/argus-probe pattern)
sys.path.insert(0, "/mmc/root/lib/pagerctl")
try:
    import pagerctl
    from pagerctl import Pager
except ImportError as exc:
    print(f"FATAL: pagerctl not importable: {exc}", file=sys.stderr, flush=True)
    sys.exit(1)

for _n in ("BTN_A", "BTN_B", "BTN_UP", "BTN_DOWN",
           "BTN_LEFT", "BTN_RIGHT", "BTN_POWER"):
    if not hasattr(pagerctl, _n) and hasattr(Pager, _n):
        setattr(pagerctl, _n, getattr(Pager, _n))

from pagerctl import (BTN_A, BTN_B, BTN_UP, BTN_DOWN,
                      BTN_LEFT, BTN_POWER,
                      BLACK, WHITE, RED, GREEN, BLUE, YELLOW, CYAN, MAGENTA)

# hotel modules
from hotel import wifi
from hotel.dhcp_watch import DhcpWatcher

# Display constants
W, H = 480, 222

# Try to find a TTF font. Fall back to bitmap if none.
def _find_font() -> str | None:
    candidates = [
        "/mmc/root/lib/pagerctl/fonts/body.ttf",
        "/mmc/root/lib/pagerctl/fonts/title.TTF",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

FONT = _find_font()


# ── helpers ───────────────────────────────────────────────────────────

def _txt(pager, x, y, s, color=WHITE, size=16):
    """Draw text - TTF if available, else bitmap fallback."""
    if FONT:
        pager.draw_ttf(x, y, str(s), color, FONT, size)
    else:
        # bitmap: size 0=5x7, 1=10x14, 2=15x21 - pick by approximate scale
        bsz = 0 if size <= 10 else (1 if size <= 18 else 2)
        pager.draw_text(x, y, str(s), color, size=bsz)


def _txt_center(pager, y, s, color=WHITE, size=16):
    if FONT:
        pager.draw_ttf_centered(y, str(s), color, FONT, size)
    else:
        bsz = 0 if size <= 10 else (1 if size <= 18 else 2)
        pager.draw_text_centered(y, str(s), color, size=bsz)


def _ascii(s: str) -> str:
    """Strip non-ASCII (pager font has no umlauts/emoji)."""
    return "".join(c if 0x20 <= ord(c) < 0x7f else "?" for c in s)


def _drain_input(pager):
    while pager.poll_input():
        pass


def _wait_button(pager, allowed=None, timeout: float | None = None) -> int:
    """Block until a button in `allowed` is pressed (or any if None).
    Returns the button code (BTN_*) or 0 on timeout.
    """
    start = time.monotonic()
    while True:
        b = pager.poll_input()
        if b and (allowed is None or b in allowed):
            return b
        if timeout is not None and (time.monotonic() - start) > timeout:
            return 0
        time.sleep(0.05)


# ── screens ───────────────────────────────────────────────────────────

def screen_splash(pager) -> None:
    pager.clear(BLACK)
    _txt_center(pager, 60,  "ARGUS HOTEL",     CYAN,   28)
    _txt_center(pager, 110, "DHCP Fingerprint Capture", WHITE, 14)
    _txt_center(pager, 140, "(no laptop required)",     YELLOW, 12)
    pager.flip()
    time.sleep(1.2)
    _drain_input(pager)


MODES = [
    ("Scan + Connect + Capture", "scan_connect_capture"),
    ("Capture only (current iface)", "capture_only"),
    ("Status / current SSID",     "status"),
    ("Exit",                       "exit"),
]


def screen_mode_picker(pager) -> str:
    selected = 0
    while True:
        pager.clear(BLACK)
        _txt_center(pager, 6, "ARGUS HOTEL", CYAN, 18)
        pager.hline(0, 30, W, CYAN)
        for i, (label, _key) in enumerate(MODES):
            y = 44 + i * 36
            color = YELLOW if i == selected else WHITE
            _txt(pager, 30, y, _ascii(label), color, 18)
            if i == selected:
                pager.fill_rect(8, y + 4, 14, 14, YELLOW)
        _txt(pager, 6, H - 18, "UP/DN: choose   A: ok   B: back", GREEN, 11)
        pager.flip()
        b = _wait_button(pager)
        if b == BTN_UP:
            selected = (selected - 1) % len(MODES)
        elif b == BTN_DOWN:
            selected = (selected + 1) % len(MODES)
        elif b == BTN_A:
            return MODES[selected][1]
        elif b in (BTN_B, BTN_POWER):
            return "exit"


def screen_scanning(pager) -> None:
    pager.clear(BLACK)
    _txt_center(pager, 80,  "Scanning networks...", WHITE, 18)
    _txt_center(pager, 110, "(iw scan, ~10s)",      YELLOW, 12)
    pager.flip()


def screen_ap_picker(pager, aps: list[dict]) -> dict | None:
    """Scrollable list of APs. Returns chosen ap-dict or None."""
    if not aps:
        pager.clear(BLACK)
        _txt_center(pager, 80,  "No networks found.", RED, 20)
        _txt_center(pager, 120, "B = back", WHITE, 14)
        pager.flip()
        _wait_button(pager, allowed=(BTN_A, BTN_B))
        return None

    sel = 0
    scroll = 0
    visible = 5
    while True:
        pager.clear(BLACK)
        _txt_center(pager, 4, "Pick a network (B=back)", CYAN, 14)
        pager.hline(0, 24, W, CYAN)
        for row in range(visible):
            idx = scroll + row
            if idx >= len(aps):
                break
            ap = aps[idx]
            y = 32 + row * 34
            is_sel = (idx == sel)
            color = YELLOW if is_sel else WHITE
            if is_sel:
                pager.fill_rect(0, y - 2, W, 30, pager.rgb(28, 28, 28))
            enc = ap["encryption"]
            enc_color = GREEN if enc == "open" else (
                YELLOW if enc == "wep" else RED)
            # signal -> short bars
            sig = ap["signal_dbm"]
            bars = 1 if sig < -80 else 2 if sig < -70 else 3 if sig < -60 else 4
            # left: bars + ssid
            pager.fill_rect(6, y + 6, 4, 18, color)
            pager.fill_rect(12, y + 10, 4, 14, color if bars >= 2 else pager.rgb(40, 40, 40))
            pager.fill_rect(18, y + 14, 4, 10, color if bars >= 3 else pager.rgb(40, 40, 40))
            pager.fill_rect(24, y + 18, 4, 6,  color if bars >= 4 else pager.rgb(40, 40, 40))
            ssid_disp = _ascii(ap["ssid"])[:24]
            _txt(pager, 36, y, ssid_disp, color, 16)
            _txt(pager, W - 80, y, enc.upper(), enc_color, 12)
            _txt(pager, W - 40, y, f"{sig}", color, 12)
        # footer
        _txt(pager, 6, H - 18,
             f"[{sel + 1}/{len(aps)}]  UP/DN scroll  A=connect  B=back",
             GREEN, 10)
        pager.flip()
        b = _wait_button(pager)
        if b == BTN_UP:
            sel = max(0, sel - 1)
            if sel < scroll:
                scroll = sel
        elif b == BTN_DOWN:
            sel = min(len(aps) - 1, sel + 1)
            if sel >= scroll + visible:
                scroll = sel - visible + 1
        elif b == BTN_A:
            return aps[sel]
        elif b in (BTN_B, BTN_POWER):
            return None


def screen_connect_progress(pager, ssid: str, ip: str | None,
                            status: str) -> None:
    pager.clear(BLACK)
    _txt_center(pager, 30, "Connecting...", CYAN, 22)
    _txt_center(pager, 70, _ascii(ssid)[:28], WHITE, 18)
    _txt_center(pager, 110, status, YELLOW, 14)
    if ip:
        _txt_center(pager, 140, f"IP: {ip}", GREEN, 16)
    pager.flip()


def screen_duration_picker(pager) -> int | None:
    """Return duration in seconds, or None on cancel."""
    options = [60, 180, 300, 600, 1200, 1800]
    labels  = ["1 min", "3 min", "5 min", "10 min", "20 min", "30 min"]
    sel = 3  # default 10 min
    while True:
        pager.clear(BLACK)
        _txt_center(pager, 8, "Capture duration", CYAN, 18)
        pager.hline(0, 32, W, CYAN)
        for i, label in enumerate(labels):
            y = 44 + i * 24
            color = YELLOW if i == sel else WHITE
            _txt(pager, 100, y, f"  {label}", color, 16)
            if i == sel:
                pager.fill_rect(80, y + 4, 12, 12, YELLOW)
        _txt(pager, 6, H - 18, "UP/DN: pick   A: start   B: back", GREEN, 11)
        pager.flip()
        b = _wait_button(pager)
        if b == BTN_UP:
            sel = (sel - 1) % len(options)
        elif b == BTN_DOWN:
            sel = (sel + 1) % len(options)
        elif b == BTN_A:
            return options[sel]
        elif b in (BTN_B, BTN_POWER):
            return None


def screen_capture(pager, iface: str, duration: int) -> tuple[dict, Path]:
    """Run DhcpWatcher and render live stats.
    Returns (final stats, pcap path)."""
    watcher = DhcpWatcher(iface=iface, duration_s=duration)
    if not watcher.start():
        pager.clear(BLACK)
        _txt_center(pager, 80, "tcpdump failed", RED, 20)
        _txt_center(pager, 120,
                    _ascii(watcher.stats.get("error") or "?")[:50],
                    WHITE, 12)
        pager.flip()
        _wait_button(pager, allowed=(BTN_A, BTN_B))
        return watcher.stats, watcher.pcap_path

    last_draw = 0.0
    try:
        while not watcher.is_done():
            now = time.monotonic()
            if now - last_draw > 0.5:
                _draw_capture(pager, watcher, iface, duration)
                last_draw = now
            b = pager.poll_input()
            if b == BTN_B:
                break
            if b == BTN_POWER:
                break
            time.sleep(0.08)
    finally:
        watcher.stop()
    # one final draw with final stats
    _draw_capture(pager, watcher, iface, duration, final=True)
    time.sleep(0.5)
    return watcher.stats, watcher.pcap_path


def _draw_capture(pager, watcher, iface, duration, final=False):
    pager.clear(BLACK)
    title = "DHCP CAPTURE" if not final else "DHCP - DONE"
    title_color = GREEN if not final else CYAN
    _txt_center(pager, 2, title, title_color, 16)
    # progress bar
    elapsed = watcher.stats["elapsed_s"]
    pct = min(1.0, elapsed / max(1, duration))
    bar_w = int((W - 20) * pct)
    pager.rect(8, 22, W - 16, 8, WHITE)
    pager.fill_rect(10, 24, bar_w, 4, GREEN)
    _txt(pager, 8, 32, f"{iface}  {int(elapsed)}s / {duration}s", WHITE, 11)
    # big counters
    _txt(pager, 8,   52, "DHCPs:", YELLOW, 16)
    _txt(pager, 110, 52, str(watcher.stats["dhcps"]), WHITE, 22)
    _txt(pager, 220, 52, "Devices:", YELLOW, 16)
    _txt(pager, 340, 52, str(watcher.stats["devices"]), WHITE, 22)
    # recent hosts list
    _txt(pager, 8, 90, "Recent:", CYAN, 12)
    hosts = watcher.stats["hosts"][:5]
    for i, (mac, host, vendor) in enumerate(hosts):
        y = 108 + i * 18
        short = mac[-8:]  # last 5 hex
        host_d = _ascii(host)[:18]
        vend_d = _ascii(vendor)[:18]
        _txt(pager, 8,   y, short,    WHITE, 11)
        _txt(pager, 80,  y, host_d,   GREEN, 11)
        _txt(pager, 240, y, vend_d,   CYAN,  11)
    # footer / error
    err = watcher.stats.get("error")
    if err:
        _txt(pager, 8, H - 16, _ascii(err)[:60], RED, 10)
    else:
        _txt(pager, 8, H - 16,
             "B = stop  -  pcap auto-saved",
             GREEN, 10)
    pager.flip()


def screen_report(pager, stats: dict, pcap_path: Path) -> None:
    pager.clear(BLACK)
    _txt_center(pager, 6, "CAPTURE COMPLETE", CYAN, 16)
    pager.hline(0, 28, W, CYAN)
    _txt(pager, 8, 38, f"DHCPs seen:  {stats['dhcps']}", WHITE, 14)
    _txt(pager, 8, 60, f"Devices:     {stats['devices']}", WHITE, 14)
    _txt(pager, 8, 82, f"PCAP: {pcap_path.name}", YELLOW, 11)
    _txt(pager, 8, 100, f"Saved to {pcap_path.parent}/", WHITE, 10)
    _txt(pager, 8, 120, "Run a regular Argus session to enrich with", WHITE, 11)
    _txt(pager, 8, 134, "Fingerbank (device-name + category).", WHITE, 11)
    if stats["devices"] == 0:
        _txt(pager, 8, 160, "0 devices: not associated, wrong VLAN,",
             YELLOW, 11)
        _txt(pager, 8, 174, "or no client joins during capture.", YELLOW, 11)
    _txt(pager, 6, H - 18, "A = back to menu   B = exit", GREEN, 11)
    pager.flip()
    b = _wait_button(pager, allowed=(BTN_A, BTN_B, BTN_POWER))
    return b


def screen_status(pager) -> None:
    pager.clear(BLACK)
    _txt_center(pager, 8, "STATUS", CYAN, 16)
    pager.hline(0, 30, W, CYAN)
    cur = wifi.current_ssid()
    cfg = wifi.configured_ssid()
    ip  = wifi.get_ipv4()
    _txt(pager, 8, 44,  "Associated SSID:", YELLOW, 14)
    _txt(pager, 8, 64,  _ascii(cur) or "(not associated)",
         GREEN if cur else RED, 16)
    _txt(pager, 8, 90,  "Configured SSID:", YELLOW, 14)
    _txt(pager, 8, 110, _ascii(cfg) or "(none)", WHITE, 14)
    _txt(pager, 8, 136, "IPv4:", YELLOW, 14)
    _txt(pager, 8, 156, ip or "(none)", GREEN if ip else RED, 14)
    _txt(pager, 6, H - 18, "any button = back", GREEN, 11)
    pager.flip()
    _wait_button(pager)


# ── orchestrators ─────────────────────────────────────────────────────

def do_scan_connect_capture(pager) -> None:
    screen_scanning(pager)
    aps = wifi.scan()
    ap = screen_ap_picker(pager, aps)
    if not ap:
        return
    # WPA = needs password = out of scope for MVP
    if ap["encryption"] != "open":
        pager.clear(BLACK)
        _txt_center(pager, 60, "WPA networks not supported", RED, 18)
        _txt_center(pager, 90, "in this MVP. Pre-config via", WHITE, 12)
        _txt_center(pager, 108, "uci on the pager + use", WHITE, 12)
        _txt_center(pager, 126, "'Capture only' mode.", WHITE, 12)
        _txt_center(pager, 170, "any button = back", GREEN, 11)
        pager.flip()
        _wait_button(pager)
        return
    # connect
    screen_connect_progress(pager, ap["ssid"], None, "uci set + wifi reload")
    if not wifi.connect(ap["ssid"], password=None):
        screen_connect_progress(pager, ap["ssid"], None, "uci FAILED")
        time.sleep(2)
        return
    # wait for DHCP
    screen_connect_progress(pager, ap["ssid"], None, "waiting for IP...")
    ip = wifi.wait_for_ip(timeout=30)
    if not ip or ip.startswith("169.254."):
        screen_connect_progress(pager, ap["ssid"], ip,
                                "no IP - DHCP failed?")
        time.sleep(2)
        # still proceed - some hotels need captive-portal interaction
        # but DHCP-capture might still see neighbours
    else:
        screen_connect_progress(pager, ap["ssid"], ip, "associated")
        time.sleep(1)
    # capture duration
    dur = screen_duration_picker(pager)
    if dur is None:
        return
    stats, pcap = screen_capture(pager,
                                 iface=wifi.CLIENT_IFACE, duration=dur)
    screen_report(pager, stats, pcap)


def do_capture_only(pager) -> None:
    dur = screen_duration_picker(pager)
    if dur is None:
        return
    iface = wifi.CLIENT_IFACE  # default; could let user pick
    stats, pcap = screen_capture(pager, iface=iface, duration=dur)
    screen_report(pager, stats, pcap)


# ── main loop ─────────────────────────────────────────────────────────

def main() -> int:
    pager = Pager()
    try:
        pager.clear(BLACK)
        pager.flip()
        screen_splash(pager)
        while True:
            mode = screen_mode_picker(pager)
            if mode == "exit":
                break
            elif mode == "scan_connect_capture":
                do_scan_connect_capture(pager)
            elif mode == "capture_only":
                do_capture_only(pager)
            elif mode == "status":
                screen_status(pager)
        # farewell
        pager.clear(BLACK)
        _txt_center(pager, 100, "Bye.", CYAN, 28)
        pager.flip()
        time.sleep(0.5)
    except Exception:
        traceback.print_exc()
        try:
            pager.clear(BLACK)
            _txt_center(pager, 60, "CRASH", RED, 24)
            _txt_center(pager, 110, "see logs/hotel.last.log", WHITE, 12)
            pager.flip()
            time.sleep(3)
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
