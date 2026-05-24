"""hotel/dhcp_watch.py - background tcpdump + live DHCP parser.

Runs tcpdump in a subprocess writing to manual_<ts>_dhcp.pcap, and a
parallel daemon thread that re-parses the growing pcap every poll_interval
seconds to update a live counter dict the UI can read.

Designed for the hotel-mode capture screen: UI reads .stats and renders
without touching tcpdump or the parser.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# Need read_pcap_dhcp from cyt
_CYT_PY = "/root/payloads/user/reconnaissance/argus-pager-2.0/cyt/python"
if _CYT_PY not in sys.path:
    sys.path.insert(0, _CYT_PY)
from pcap_engine import read_pcap_dhcp  # type: ignore


PCAP_DIR_DEFAULT = "/root/loot/argus/pcap"


class DhcpWatcher:
    """Runs tcpdump + a polling parser thread until stop() is called."""

    def __init__(self, iface: str, duration_s: int,
                 pcap_dir: str = PCAP_DIR_DEFAULT,
                 poll_interval: float = 2.0):
        self.iface = iface
        self.duration_s = duration_s
        self.pcap_dir = pcap_dir
        self.poll_interval = poll_interval
        os.makedirs(pcap_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        self.pcap_path = Path(pcap_dir) / f"manual_{ts}_dhcp.pcap"
        self.start_ts: float | None = None
        self.proc: subprocess.Popen | None = None
        self._stop_evt = threading.Event()
        self._parser_thread: threading.Thread | None = None
        # Live stats - readable from UI without locking (single writer)
        self.stats: dict = {
            "dhcps":   0,                 # total DHCP frames parsed
            "devices": 0,                 # unique MACs
            "hosts":   [],                # list[(mac, hostname, vendor)] sorted by last_seen
            "elapsed_s": 0.0,
            "error":   None,              # set if tcpdump fails to start
            "raw":     {},                # full {mac: detail} from read_pcap_dhcp
        }

    # ── lifecycle ─────────────────────────────────────────────────────

    def start(self) -> bool:
        """Spawn tcpdump + parser thread. Returns False if pre-flight fails."""
        # Filter to DHCP only - keeps pcap small + parser cheap
        cmd = [
            "tcpdump", "-i", self.iface, "-w", str(self.pcap_path),
            "-U", "-s", "1500", "-q", "udp port 67 or udp port 68",
        ]
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except Exception as e:
            self.stats["error"] = f"tcpdump spawn failed: {e}"
            return False
        # Brief sanity check that tcpdump didn't exit immediately
        time.sleep(0.3)
        if self.proc.poll() is not None:
            try:
                err = self.proc.stderr.read().decode("utf-8", "replace")[:120]
            except Exception:
                err = "?"
            self.stats["error"] = f"tcpdump died: {err.strip()}"
            return False
        self.start_ts = time.monotonic()
        self._parser_thread = threading.Thread(
            target=self._parser_loop, daemon=True)
        self._parser_thread.start()
        return True

    def stop(self) -> None:
        self._stop_evt.set()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        if self._parser_thread:
            self._parser_thread.join(timeout=3)
        # Final parse pass so stats reflect every captured frame
        self._parse_once()

    def remaining_s(self) -> int:
        if self.start_ts is None:
            return self.duration_s
        return max(0, int(self.duration_s - (time.monotonic() - self.start_ts)))

    def is_done(self) -> bool:
        """True if duration elapsed, tcpdump died, or stop() was called."""
        if self._stop_evt.is_set():
            return True
        if self.start_ts is not None and \
           (time.monotonic() - self.start_ts) >= self.duration_s:
            return True
        if self.proc and self.proc.poll() is not None:
            return True
        return False

    # ── parser loop ───────────────────────────────────────────────────

    def _parser_loop(self) -> None:
        while not self._stop_evt.is_set():
            self._parse_once()
            # short sleeps so stop() reacts quickly
            for _ in range(int(self.poll_interval / 0.1)):
                if self._stop_evt.is_set():
                    return
                time.sleep(0.1)

    def _parse_once(self) -> None:
        try:
            raw = read_pcap_dhcp(str(self.pcap_path))
        except Exception as e:
            self.stats["error"] = f"parse: {e}"
            return
        total = sum(d.get("count", 0) for d in raw.values())
        # Sort hosts by last_seen desc - newest at top
        items = sorted(raw.items(),
                       key=lambda kv: kv[1].get("last_seen", ""),
                       reverse=True)
        hosts = [(mac, (d.get("hostname") or "-"),
                  (d.get("vendor") or "-"))
                 for mac, d in items]
        self.stats["raw"]     = raw
        self.stats["dhcps"]   = total
        self.stats["devices"] = len(raw)
        self.stats["hosts"]   = hosts
        if self.start_ts is not None:
            self.stats["elapsed_s"] = time.monotonic() - self.start_ts


if __name__ == "__main__":
    # Smoke-test: capture 5s on lo (nothing to capture - just checks lifecycle)
    w = DhcpWatcher(iface="lo", duration_s=5)
    print("start:", w.start(), " pcap:", w.pcap_path)
    if w.start_ts is None:
        print("error:", w.stats.get("error"))
    else:
        while not w.is_done():
            time.sleep(1)
            print(f"  t={w.stats['elapsed_s']:.0f}s "
                  f"dhcps={w.stats['dhcps']} devs={w.stats['devices']}")
    w.stop()
    print("final:", w.stats)
