# Troubleshooting — argus-pager 3.0

Haeufige Fehler aus Discord-Anfragen und wie du sie fixt. Suche mit
`Ctrl+F` nach deinem Fehlertext.

---

## SSH / Netzwerk

### `ssh: connect to host 172.16.52.1 port 22: Connection timed out`
- Pager laeuft nicht / nicht per Kabel verbunden
- Falsche IP (Pager-Firmware 2.0 hat die Default-IP evtl. geaendert — pruefen in Pager-Settings-Menu → Mgmt-IP)
- Firewall auf Laptop blockiert

### `ssh: connect to host 172.16.0.1 port 22: Connection timed out` (Mudi)
- Mudi aus / nicht im WLAN
- Mudi-LAN-IP geaendert (default war `192.168.8.1`, oft auf `172.16.0.1` o.ae. gelegt wegen Router-Konflikt). Pruefe im GL.iNet-Web-UI → Network → LAN

### `Permission denied (publickey)` auf Mudi, Pager geht aber
Haeufigster Discord-Fehler. **Mudi nutzt Dropbear**, nicht OpenSSH:

```bash
# FALSCH:
ssh mudi 'cat >> /root/.ssh/authorized_keys'

# RICHTIG:
cat ~/.ssh/mudi_key.pub | ssh root@172.16.0.1 \
    'cat >> /etc/dropbear/authorized_keys'
```

### `scp` zum Mudi haengt / `subsystem request failed`
Dropbear hat **keinen sftp-server**. Statt scp:

```bash
# Einzelne Datei:
cat local.py | ssh mudi 'cat > /root/raypager/python/local.py'

# Ganzer Ordner:
tar -cz raypager/ | ssh mudi 'cd /root && tar -xz'
```

### Pager verbindet nach Reboot nicht mit Mudi-WiFi (`wlan0cli` DOWN)
Fix in `/etc/rc.local` auf dem Pager:

```bash
ssh pager 'grep -q "ifup cli" /etc/rc.local || \
    sed -i "/^exit 0/i sleep 20 \&\& ifup cli 2>/dev/null \&" \
    /etc/rc.local'
```

Workaround einmalig: `ssh pager 'wifi down && wifi up'`

---

## Clone / Submodules

### `fatal: not a git repository` bei `git config core.hooksPath hooks`
Du bist nicht im Repo-Root. `cd argus-pager-3.0` zuerst.

### `cyt/` und `raypager/` sind leer nach Clone
Du hast `--recurse-submodules` vergessen. Nachtraeglich:

```bash
cd argus-pager-3.0
git submodule update --init --recursive
```

### Clone bricht ab mit `fatal: unable to access ... SSL certificate problem`
Auf dem Pager — und du solltest nicht auf dem Pager clonen (zu wenig RAM/Flash).
Clone auf dem **Laptop**, dann SCP.

---

## Deployment auf Pager

### `bad interpreter: No such file or directory` beim Payload-Start
CRLF-Line-Endings nach SCP von Windows. Fix:

```bash
ssh pager 'find /root/payloads/user/reconnaissance/argus-pager-3.0 \
    -type f \( -name "*.sh" -o -name "*.py" \) \
    -exec sed -i "s/\r//" {} \;'
```

### Permissions `--w--w--wx` nach SCP von Windows
`umask` von Windows ist strange. Fix:

```bash
ssh pager 'chmod -R u+rX,go+rX /root/payloads/user/reconnaissance/argus-pager-3.0'
ssh pager 'chmod 755 /root/payloads/user/reconnaissance/argus-pager-3.0/payload.sh'
```

### `pagerctl.so: cannot open shared object file`
Loki oder Pagergotchi ist nicht installiert. Pruefe:

```bash
ssh pager 'ls /mmc/root/lib/pagerctl/'
```

Keine Dateien → zuerst Loki (`https://github.com/dark-lbp/loki`)
installieren, dann argus-pager erneut starten.

### `payload.sh: exit 7`
Framework-Builtin-Fehler. Haeufige Ursachen:

1. **DuckyScript-Builtins im Shell-Context** — die funktionieren
   nur, wenn das Script vom Pager-Payload-Loader gestartet wird,
   **nicht** aus einer SSH-Shell. `ssh pager '/root/.../payload.sh'`
   wird fehlschlagen.
2. **`$DUCKYSCRIPT_CANCELLED` ist leer** — die Variable ist nur im
   Framework gesetzt. Nutze `[ $? -ne 0 ] && break` als Fallback.
3. **Pager-Firmware < 2.0** — manche Builtins (z.B. `WIFI_PCAP_START`
   mit Multi-Band) brauchen Firmware 2.0.

### `payload.sh` nach dem Starten sofort auf Haupt-Menu zurueck
Hook am Payload-Ende fehlt. Letzte Zeile MUSS sein:

```bash
exit 0
```

Nicht nur `break` aus einer `while`-Schleife, sondern `exit 0` am
Script-Ende.

---

## Scan / Report

### Scan laeuft, aber Report ist leer / "CYT analysis failed"
Submodules nicht initialisiert. Nach `git clone` ohne `--recurse-submodules`
sind `cyt/python/*.py` nicht da.

```bash
ssh pager 'cd /root/payloads/user/reconnaissance/argus-pager-3.0 && \
    ls cyt/python/analyze_pcap.py'
```

Keine Datei → Submodules auf Laptop initialisieren und erneut
hochladen.

### Scan laeuft, aber `payload.sh` wurde SIGKILLed (Akku weg / Timeout)
Report nachtraeglich bauen aus den PCAPs:

```bash
ssh pager 'cd /root/payloads/user/reconnaissance/argus-pager-3.0 && \
    python3 tools/rerun_analyser.py <session_id>'
# session_id = Filename-Prefix im PCAP-Ordner, z.B. 20261101_143022
```

### Alle BT-Geraete sind "Unknown Vendor"
OUI-Cache leer. Beim ersten Lauf lädt `cyt/python/oui_lookup.py` den
Cache (~16000 OUIs) und speichert ihn fuer 365 Tage. Dauert einmalig
30-60 s mit WiFi. Ohne Internet: OUI-Lookup bleibt leer.

### WiFi-Report zeigt keine 5/6-GHz-Probes
- Pager-WiFi-Chip kann 5/6 GHz nicht → nur 2.4 GHz-Band wird gescannt
- Multi-Band-Capture braucht Firmware 2.0+

### GPS gibt `NO FIX`
- Dongle drinnen? Antenne ans Fenster oder nach draussen
- 60-120 s warten (Cold-Start)
- Mudi 7 (E5800) nutzt ggf. internes GPS statt USB — in `config.json`
  Mudi-Modell korrekt setzen

### `OpenCelliD: UNKNOWN` fuer alle Tuerme
- Dein Provider ist nicht in der OpenCelliD-DB (bei kleinen MVNOs
  oder manchen Laendern haeufig — BITE/labas in LT z.B.)
- Argus sammelt die Messungen in `/root/loot/raypager/upload_queue/`;
  per Upload-Menu einreichen → nach ein paar Tagen tauchen sie in der
  DB auf

---

## Pager-GUI / Mgmt-Interface

### Port 1471 nicht erreichbar ueber Mudi-WiFi
Firewall blockiert WAN→LAN. SSH-Tunnel:

```bash
ssh -L 1471:localhost:1471 pager
# dann im Browser: http://localhost:1471
```

Oder langfristig: nftables-Regel fuer dein Mudi-Subnet in der
Pager-Firewall-Config.

### Mgmt-Interface zeigt leere Payload-Liste
`/root/payloads/user/reconnaissance/` hat kein `.meta`-File. Pruefe:

```bash
ssh pager 'ls /root/payloads/user/reconnaissance/argus-pager-3.0/.meta'
```

Fehlt → vom Repo erneut hochladen.

---

## OPSEC-Hook

### Commit scheitert mit `[OPSEC FAIL]`
Der pre-commit hat eine echte MAC, GPS-Coord oder einen API-Key
gefunden. Lies die Hook-Ausgabe, sie nennt die genaue Datei + Zeile.

**Darfst du committen** (von `hooks/pre-commit` als Platzhalter akzeptiert):

- `aa:bb:cc:dd:ee:xx` (xx = beliebig)
- `aa:00:00:00:00:xx`
- `ca:fe:ca:fe:xx:xx`
- `de:ad:be:ef:xx:xx`
- `11:22:33:44:55:66`
- `bc:bc:bc:bc:bc:bc`
- `01:02:03:04:05:06`
- `00:00:00:00:00:00`
- `ff:ff:ff:ff:ff:ff`

Alles andere wird als echte MAC gewertet. GPS-Platzhalter: `0.000000, 0.000000`.
Die genaue Regex steht in `hooks/pre-commit` — ergaenze dort, falls du
weitere Dummy-Patterns brauchst.

### Hook laeuft gar nicht (Commit geht einfach durch)
`core.hooksPath` nicht gesetzt:

```bash
cd argus-pager-3.0
git config core.hooksPath hooks
```

---

## IMEI-Rotation / Blue Merle

### `blue-merle: command not found`
Nicht installiert. Je nach Mudi-Modell:

**Mudi V2 (GL-E750V2):**

```bash
ssh mudi 'opkg update && opkg install blue-merle'
```

**Mudi 7 (GL-E5800):** nicht im Standard-Repo. Nutze den Community-Fork
[WSchlesner/blue-merle-v2](https://github.com/WSchlesner/blue-merle-v2):

```bash
# .ipk aus den GitHub-Releases laden, dann:
scp -O blue-merle-v2_*.ipk root@172.16.0.1:/tmp/
ssh mudi 'opkg install /tmp/blue-merle-v2_*.ipk'
ssh mudi 'blue-merle check'
```

LuCI muss vor dem Install einmalig per GL.iNet-UI aktiviert werden
(*System → Advanced Settings → Install Now*), sonst fehlt der
`uhttpd`-Daemon und die LuCI-Seite ist nicht erreichbar.

### `rotate` haengt / Modem-Disconnect kaputt
Vor Rotation Radio ausschalten:

```bash
ssh mudi 'gl_modem radio off && sleep 2 && blue-merle rotate && \
          sleep 2 && gl_modem radio on'
```

Pager braucht nach Rotation einen Reboot, sonst keep alive-Session
noch mit alter IMEI.

---

## Noch Fragen?

- **GitHub Issues:** https://github.com/tschakram/argus-pager-3.0/issues
- **Discord:** (dein Server-Link hier)
- **Vorgaenger-Projekte:**
  - [argus-pager](https://github.com/tschakram/argus-pager) (1.x)
  - [argus-pager-2.0](https://github.com/tschakram/argus-pager-2.0)
