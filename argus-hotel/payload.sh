#!/bin/bash
# argus-hotel - Pager-native DHCP-Fingerprint capture for Hotel/Cafe.
#
# Bedienung komplett am Pager (kein Laptop, kein SSH). Operator und
# private Geraete bleiben aus dem (potentiell schadhaften) Hotel-WiFi.
#
# Workflow:
#   1. SSID-Scan + Connect (Open-WLAN per Button-Klick)
#      ODER: 'Capture only' fuer bereits assoziierte Verbindung
#   2. tcpdump filtert UDP 67/68, live-Counter waehrend Capture
#   3. PCAP landet in /root/loot/argus/pcap/manual_<ts>_dhcp.pcap
#   4. Naechste Argus-Session enriched die Daten via Fingerbank.

LOG_DIR=/root/loot/argus/logs
mkdir -p "$LOG_DIR" 2>/dev/null
LOG_FILE="$LOG_DIR/hotel.$(date +%Y%m%d_%H%M%S).log"
ln -sf "$LOG_FILE" "$LOG_DIR/hotel.last.log"
exec >"$LOG_FILE" 2>&1
set -x
echo "=== argus-hotel launch $(date) ==="

ARGUS_DIR="/root/payloads/user/reconnaissance/argus-pager-2.0"
if [ ! -d "$ARGUS_DIR/python/hotel" ]; then
    echo "FATAL: $ARGUS_DIR/python/hotel/ fehlt - argus-pager-2.0 deploy noetig."
    exit 1
fi
cd "$ARGUS_DIR"

export PATH="/mmc/usr/bin:/mmc/usr/sbin:/mmc/bin:/mmc/sbin:/usr/bin:/usr/sbin:/bin:/sbin:$PATH"
export LD_LIBRARY_PATH="/mmc/root/lib/pagerctl:/mmc/usr/lib:/mmc/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$ARGUS_DIR/python:/mmc/root/lib/pagerctl:${PYTHONPATH:-}"
export ARGUS_PAYLOAD_DIR="$ARGUS_DIR"

# Pre-Flight
for bin in python3 tcpdump iw uci wifi; do
    command -v "$bin" >/dev/null 2>&1 || { echo "PRE-FLIGHT FAIL: missing $bin"; exit 1; }
done
[ -f /mmc/root/lib/pagerctl/pagerctl.py ] || {
    echo "PRE-FLIGHT FAIL: pagerctl missing - install pineapple_pager_pagerctl"
    exit 1
}

# Snapshot current wlan0cli config so we can restore on exit
# (so the user doesn't lose the Mudi-cli SSID after the hotel session)
WLAN_BACKUP="/tmp/argus_hotel_wlan_backup.uci"
uci show wireless.wlan0cli > "$WLAN_BACKUP" 2>/dev/null || true
echo "wlan0cli backup -> $WLAN_BACKUP"

# Emergency recovery script (callable via ssh if framework crashes)
KILL_SCRIPT="$LOG_DIR/hotel_kill.sh"
cat > "$KILL_SCRIPT" << 'KILL_EOF'
#!/bin/sh
echo "killing hotel python..."
pkill -9 -f "hotel/main.py" 2>/dev/null
pkill -9 tcpdump 2>/dev/null
sleep 1
# Restore Mudi wlan config from snapshot (best effort)
if [ -f /tmp/argus_hotel_wlan_backup.uci ]; then
    while IFS= read -r line; do
        uci set "${line#wireless.wlan0cli.}" 2>/dev/null || true
    done < /tmp/argus_hotel_wlan_backup.uci
    uci commit wireless 2>/dev/null
    wifi reload 2>/dev/null
fi
PINEAPPLE_PID=$(ps w | awk '/\/pineapple\/pineapple/ && !/awk/ {print $1; exit}')
[ -n "$PINEAPPLE_PID" ] && kill -CONT "$PINEAPPLE_PID" 2>/dev/null
echo "framework resumed (PID $PINEAPPLE_PID)"
KILL_EOF
chmod +x "$KILL_SCRIPT"

# Pause framework UI
PINEAPPLE_PID=$(ps w | awk '/\/pineapple\/pineapple/ && !/awk/ {print $1; exit}')
echo "pineapple-pid=$PINEAPPLE_PID"
[ -n "$PINEAPPLE_PID" ] && kill -STOP "$PINEAPPLE_PID"

restore() {
    rc=$?
    echo "[trap rc=$rc] cleaning up..."
    pkill tcpdump 2>/dev/null
    # Restore Mudi WLAN config (so wlan0cli still talks to Mudi after exit)
    if [ -f "$WLAN_BACKUP" ]; then
        echo "restoring wlan0cli to pre-hotel config"
        while IFS= read -r line; do
            key="${line%%=*}"
            val="${line#*=}"
            # Strip outer quotes uci adds in show output
            val="${val#\'}"; val="${val%\'}"
            uci set "${key}=${val}" 2>/dev/null || true
        done < "$WLAN_BACKUP"
        uci commit wireless 2>/dev/null
        wifi reload 2>/dev/null
    fi
    [ -n "$PINEAPPLE_PID" ] && kill -CONT "$PINEAPPLE_PID" 2>/dev/null || true
    pgrep -f "/pineapple/pineapple" >/dev/null || /etc/init.d/pineapplepager start 2>/dev/null
    sleep 1
}
trap restore EXIT INT TERM HUP

echo "-> python3 -u python/hotel/main.py"
timeout --signal=TERM --kill-after=10s 7200 \
    python3 -u "$ARGUS_DIR/python/hotel/main.py"
rc=$?
echo "hotel/main.py exited with rc=$rc"
exit "$rc"
