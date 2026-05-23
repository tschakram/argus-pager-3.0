#!/bin/bash
# tools/hotel_dhcp_capture.sh
#
# Manueller DHCP-Capture fuer Hotel-Test. Muss auf dem Pager auf einem
# Interface laufen das mit dem Hotel/Cafe-WiFi assoziiert ist (NICHT
# wlan0cli, das ist die Mudi-Verbindung).
#
# Workflow:
#   1. Pager mit Ziel-WiFi assoziieren (z.B. via uci wifi config, oder
#      die Pineapple-UI - hier individuell pro Setup).
#   2. Dieses Skript starten: ./hotel_dhcp_capture.sh wlan1 300
#   3. Pcap landet in /root/loot/argus/pcap/manual_<ts>_dhcp.pcap
#   4. Naechster Argus-Run findet die Datei automatisch im pcap-dir
#      und external_intel.run() extrahiert die DHCP-Fingerprints.
#
# Default-Filter: UDP 67/68 + Hostname/Vendor in den DHCP-Optionen.
# snaplen=1500 - voller Frame, damit alle DHCP-Options drin sind.

set -e

IFACE="${1:-wlan0}"
DUR="${2:-300}"
LOOT="${LOOT_DIR:-/root/loot/argus/pcap}"
TS=$(date +%Y%m%d_%H%M%S)
OUT="${LOOT}/manual_${TS}_dhcp.pcap"

mkdir -p "$LOOT"

# Pre-flight
if ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "ERROR: interface $IFACE does not exist" >&2
    exit 2
fi
if ! command -v tcpdump >/dev/null; then
    echo "ERROR: tcpdump not in PATH" >&2
    exit 2
fi

echo "Capturing DHCP on $IFACE for ${DUR}s -> $OUT"
echo "  (Ctrl-C to abort. Use tail -f to watch progress.)"

timeout "$DUR" tcpdump -i "$IFACE" -w "$OUT" -U -s 1500 -q \
    "udp port 67 or udp port 68" 2>&1 | grep -v "verbose output" || true

if [ -s "$OUT" ]; then
    echo ""
    echo "DONE. PCAP saved to $OUT ($(stat -c %s "$OUT") bytes)"
    echo "Next Argus run will auto-parse it via external_intel."
else
    echo "WARNING: empty pcap - no DHCP frames seen on $IFACE in $DUR s"
    rm -f "$OUT"
    exit 1
fi
