# Installation — argus-pager 3.0

Diese Anleitung begleitet dich Schritt fuer Schritt vom unverpackten
Pager bis zum ersten Scan. Lies sie einmal durch, bevor du anfaengst.

> Du hast einen Fehler oder etwas haengt? Siehe [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
> Fuer die neuesten Discord-FAQ: schau zuerst dort rein.

---

## 1. Was du brauchst

### Hardware

| Teil | Modell / Spezifikation | Bezug |
|---|---|---|
| **WiFi Pineapple Pager** | Firmware **2.0** oder neuer | hak5.org |
| **GL-iNet Mudi** | V2 (**GL-E750V2**, 4G LTE) **oder** Mudi 7 (**GL-E5800**, 5G) | gl-inet.com |
| **GNSS-USB-Dongle** | u-blox M8130 (empfohlen) oder jeder NMEA-faehige USB-GPS | Amazon/eBay |
| **USB-A auf USB-A Kabel** | fuer Pager <-> Laptop (SSH + Mgmt) | - |
| **Micro-USB Kabel** | fuer Mudi V2 (bzw. USB-C fuer Mudi 7) | - |
| **SIM-Karte** | Daten-SIM mit Roaming (fuer LTE/5G + OpenCelliD-Uploads) | Provider |

### Software-Voraussetzungen auf dem Pager

argus-pager 3.0 nutzt die **pagerctl**-Bibliothek fuer die native UI
(Framebuffer, Fonts, Input). Die wird **nicht** von diesem Repo
installiert, sondern von einem der zwei Pager-Launcher mitgebracht:

- **Loki** (empfohlen, offizielle Pineapple-Firmware-2.0 kompatibel) — `https://github.com/dark-lbp/loki`
- **Pagergotchi** — alternativ, aelter

Pfad nach Installation: `/mmc/root/lib/pagerctl/libpagerctl.so` und
`/mmc/root/lib/pagerctl/pagerctl.py`. Pruefe mit:

```bash
ssh pager 'ls /mmc/root/lib/pagerctl/'
```

Siehst du beide Dateien nicht, musst du zuerst Loki oder Pagergotchi
installieren — ohne pagerctl startet die UI nicht.

### Software-Voraussetzungen auf dem Laptop

- `git` (fuer Clone und Submodules)
- `ssh` / `scp` (nicht `putty` — die Scripts gehen von OpenSSH-Syntax aus)
- `gh` (optional, GitHub CLI; nur wenn du Repo-Forks machen willst)

### Software-Voraussetzungen auf dem Mudi

Alles ab Werk vorhanden:
- `python3` (3.10+)
- `curl` (kein `ssl`-Modul in Python verfuegbar — darum curl-Fallback)
- `gl_modem` (GL.iNet-Modem-CLI)
- `dropbear` (SSH-Server)

Fuer IMEI-Rotation zusaetzlich:
- **Blue Merle** Paket — `opkg install blue-merle` oder manuell aus
  `https://github.com/srlabs/blue-merle` (fuer E5800 ggf. nach eigenem Build)

---

## 2. SSH-Zugang einrichten

### 2.1 Keys erzeugen (auf dem Laptop)

Falls du noch keine hast — pro Geraet einen eigenen Key:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/pager_key -N ""
ssh-keygen -t ed25519 -f ~/.ssh/mudi_key  -N ""
```

### 2.2 Pager (Public-Key eintragen)

Pager ist beim ersten Boot per Kabel unter **172.16.52.1** erreichbar,
Default-Login `root` ohne Passwort.

```bash
ssh-copy-id -i ~/.ssh/pager_key.pub root@172.16.52.1
```

Falls `ssh-copy-id` fehlt, manuell:

```bash
cat ~/.ssh/pager_key.pub | ssh root@172.16.52.1 \
    'mkdir -p /root/.ssh && cat >> /root/.ssh/authorized_keys'
```

### 2.3 Mudi (Public-Key eintragen)

> **Wichtig:** der Mudi nutzt **Dropbear**, nicht OpenSSH. Die
> `authorized_keys` liegt in `/etc/dropbear/authorized_keys`, **NICHT**
> in `~/.ssh/authorized_keys`. Haeufigster Discord-Fehler.

Mudi ist unter **172.16.0.1** erreichbar (ab Werk ggf. `192.168.8.1`,
siehe LAN-IP im GL.iNet-Web-UI). Default-Login `root` + Passwort aus
dem Web-UI.

```bash
cat ~/.ssh/mudi_key.pub | ssh root@172.16.0.1 \
    'cat >> /etc/dropbear/authorized_keys'
```

### 2.4 SSH-Config (Laptop)

Lege `~/.ssh/config` an (oder ergaenze):

```sshconfig
Host pager
    HostName 172.16.52.1
    User root
    IdentityFile ~/.ssh/pager_key
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR

Host mudi
    HostName 172.16.0.1
    User root
    IdentityFile ~/.ssh/mudi_key
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
```

Test:

```bash
ssh pager 'uname -a; cat /etc/openwrt_release | head -3'
ssh mudi  'uname -a; cat /etc/openwrt_release | head -3'
```

Beide muessen antworten. Timeout = Hardware aus / falsche IP /
Firewall; "Permission denied" = Key noch nicht eingetragen.

---

## 3. argus-pager 3.0 auf dem Pager installieren

### 3.1 Clone (vom Laptop aus, nicht auf dem Pager!)

Der Pager hat **wenig Memory** und meistens **kein git**. Clone den
Repo auf dem Laptop und spiele die Files per SCP rueber.

```bash
cd ~/Projects   # oder wo auch immer
git clone --recurse-submodules \
    https://github.com/tschakram/argus-pager-3.0.git
cd argus-pager-3.0
git config core.hooksPath hooks   # OPSEC pre-commit aktivieren
```

### 3.2 Deployment auf den Pager

```bash
ssh pager 'mkdir -p /root/payloads/user/reconnaissance/argus-pager-3.0'
scp -r ./* pager:/root/payloads/user/reconnaissance/argus-pager-3.0/
```

**CRLF-Fix** (nach jedem SCP von Windows aus — sonst fail mit
`bad interpreter`):

```bash
ssh pager 'find /root/payloads/user/reconnaissance/argus-pager-3.0 \
    -type f \( -name "*.sh" -o -name "*.py" \) \
    -exec sed -i "s/\r//" {} \;'
ssh pager 'chmod 755 /root/payloads/user/reconnaissance/argus-pager-3.0/payload.sh'
```

### 3.3 config.json anlegen

```bash
ssh pager 'cd /root/payloads/user/reconnaissance/argus-pager-3.0 && \
    cp config.example.json config.json'
```

Dann API-Keys und (optional) Home-Zonen eintragen — siehe
[Abschnitt 5](#5-api-keys-eintragen).

### 3.4 Loot-Verzeichnisse anlegen

```bash
ssh pager 'mkdir -p /root/loot/argus/{pcap,reports,logs,ignore_lists,incidents,screenshots}'
```

### 3.5 Erste Ignore-Liste (deine eigenen Geraete)

```bash
ssh pager 'cp /root/payloads/user/reconnaissance/argus-pager-3.0/cyt/ignore_lists/mac_list.example.json \
             /root/loot/argus/ignore_lists/mac_list.json'
```

Dann per `ssh pager vi /root/loot/argus/ignore_lists/mac_list.json` die
MACs deiner **eigenen** Geraete eintragen (Smartphone, Kopfhoerer,
Smartwatch, Auto, …) — sonst sehen die bei jedem Scan wie Verfolger aus.

---

## 4. Mudi einrichten

### 4.1 Python-Scripts auf den Mudi uebertragen

> **Wichtig:** `scp` zum Mudi funktioniert **nicht** (kein `sftp-server`
> in dropbear). Nutze stattdessen `cat`-Pipe:

```bash
tar -cz raypager/ | ssh mudi 'mkdir -p /root/raypager && cd /root && tar -xz'
```

Dann die Config:

```bash
ssh mudi 'cd /root/raypager && cp config.example.json config.json'
# Keys und Mudi-Modell (v2 vs 7) eintragen
```

### 4.2 Mudi-Modell erkennen

```bash
ssh mudi 'cat /tmp/sysinfo/model 2>/dev/null; cat /proc/device-tree/model 2>/dev/null'
```

- Antwort enthaelt `E750V2` → Mudi V2 (4G LTE)
- Antwort enthaelt `E5800`  → Mudi 7 (5G)

Diesen Wert in `/root/raypager/config.json` als `"mudi_model": "e750v2"`
bzw. `"e5800"` eintragen (Auto-Detect kommt in alpha1).

### 4.3 GPS-Dongle checken

```bash
ssh mudi 'ls /dev/ttyACM* /dev/ttyUSB*'
# erwartet mindestens /dev/ttyACM0 fuer u-blox
ssh mudi 'cat /dev/ttyACM0 | head -5'
# erwartet NMEA-Zeilen wie $GPGGA,… — sonst GPS-Antenne reinbringen
```

### 4.4 Blue Merle (optional, fuer IMEI-Rotation)

**Nur** wenn du IMEI-Rotation wirklich brauchst — in vielen Laendern
rechtlich **grau bis illegal**. Siehe lokales Recht.

#### Mudi V2 (GL-E750V2) — SRLabs Blue Merle

```bash
ssh mudi 'opkg update && opkg install blue-merle'
# Nach Reboot pruefen:
ssh mudi 'blue-merle status'
```

Quelle: [srlabs/blue-merle](https://github.com/srlabs/blue-merle) — der
originale Fork fuer den Mudi V2 mit USB-Modem.

#### Mudi 7 (GL-E5800) — Blue Merle v2 (Community-Fork)

Fuer den Mudi 7 ist Blue Merle **komplett neu geschrieben**, weil der
Mudi 7 einen Quectel RG650V-NA mit integriertem MHI-Modem hat (statt USB
beim V2) und eine andere `gl_modem`-API. Fork:
[WSchlesner/blue-merle-v2](https://github.com/WSchlesner/blue-merle-v2)
(GPL-2.0, aktiv gepflegt, Firmware-Target GL.iNet 4.8.3/4.8.5).

Neu gegenueber V1:
- **Dual-IMEI** (SIM 1 + SIM 2/eSIM, je `AT+EGMR` per Slot)
- Drei Modi: **Random** (Luhn-valid + TAC-matched), **Deterministic**
  (stabil per IMSI-Hash), **Static** (user-supplied IMEI)
- **Consistent wireless identity** — alle BSSIDs mit einem OUI,
  SSID-Marke passend (kein impossible vendor mix)
- **Two-stage SIM swap** — throwaway IMEIs vor Poweroff, finale IMEIs
  beim naechsten Boot vor erster Modem-Attach
- **Volatile client-MACs** (`tmpfs` ueber GL.iNet Client-MAC-DB —
  Device-History landet nicht im Flash)
- **LuCI-UI** unter *Services → Blue Merle* (nicht nur CLI)
- **Touchscreen-Trigger** — 2 s Longpress auf die Uhr startet SIM-Swap
- `blue-merle check` — 16-point self-test

Install:

```bash
# LuCI aktivieren (einmalig im GL.iNet-Web-UI):
#   System → Advanced Settings → Install Now
#   -> dann unter http://<mudi-ip>:8080 erreichbar

# Release-Paket von GitHub holen (auf Laptop) und auf Mudi uebertragen:
# https://github.com/WSchlesner/blue-merle-v2/releases
scp -O blue-merle-v2_1.0.0-Script-Local.ipk root@172.16.0.1:/tmp/
ssh mudi 'opkg install /tmp/blue-merle-v2_1.0.0-Script-Local.ipk'

# Verifizieren + erste Rotation:
ssh mudi 'blue-merle check && blue-merle status'
ssh mudi 'blue-merle rotate'
```

> Firmware-Upgrades auf dem Mudi 7 entfernen das Paket **ohne**
> Uninstall-Hooks → nach jedem Firmware-Upgrade neu installieren.
> `/etc/config/blue-merle` bleibt erhalten, Factory-State ist safe.

argus-pager 3.0 ruft `blue-merle rotate` identisch zum V1 auf — die
CLI ist absichtlich kompatibel. Dual-Slot-Flags (`--slot1=random
--slot2=deterministic`) sind optional.

### 4.5 Loot-Verzeichnisse auf Mudi

```bash
ssh mudi 'mkdir -p /root/loot/raypager/{cell_cache,reports,upload_queue}'
```

### 4.6 Mudi-rc.local-Fix (persistent)

Damit der Blue-Merle-Symlink Reboots ueberlebt:

```bash
ssh mudi 'grep -q blue-merle /etc/rc.local || \
    sed -i "/^exit 0/i ln -sf /mnt/disk/upper/lib/blue-merle /lib/blue-merle 2>/dev/null" \
    /etc/rc.local'
```

---

## 5. API-Keys eintragen

Alle optional, aber ohne Keys fehlt die externe Intel-Anreicherung.

| Dienst | Wofuer | Preis | Registrierung |
|---|---|---|---|
| **Shodan InternetDB** | WAN-IP → bekannte CVEs/Ports | kostenlos (Rate-Limit) | account.shodan.io |
| **Shodan** (full) | Deep IP-Intel | $49 lifetime | account.shodan.io |
| **Fingerbank** | DHCP-Fingerprint → Hersteller+Modell | kostenlos | api.fingerbank.org |
| **OpenCelliD** | Cell-ID → GPS-Position + "unbekannter Tower"-Flag | kostenlos | opencellid.org/register |
| **WiGLE** | SSID+MAC → bekannter Standort (opt) | kostenlos (API-Quota) | wigle.net |

Eintragen in `/root/payloads/user/reconnaissance/argus-pager-3.0/config.json`:

```jsonc
{
  "shodan_api_key":     "",
  "fingerbank_api_key": "",
  "opencellid_key":     "",
  "wigle_name":         "",
  "wigle_token":        "",
  "watch_list": {
    "default_zone_radius_m": 100,
    "zones": [
      // { "name": "Home", "lat": 0.000000, "lon": 0.000000 }
    ]
  }
}
```

OpenCelliD-Key zusaetzlich in `/root/raypager/config.json` auf dem
**Mudi** (fuer Upload-Queue):

```jsonc
{ "opencellid_key": "..." }
```

> **OPSEC-Warnung:** config.json ist `gitignored`. Niemals committen —
> der pre-commit-hook blockiert es, aber vorsichtshalber immer
> `git status` vor jedem Commit.

---

## 6. Erster Scan

### 6.1 Vom Pager-Menu starten

Pager einschalten → Hauptmenue → **Payloads** → **User** →
**reconnaissance** → **argus-pager-3.0** → Button **A** (SCAN).

Was du siehst:
1. **Splash** mit Sensor-Self-Check (WiFi 2.4/5/6, BT, GPS, Cell)
2. **Ready: AUTO** — alles was gruen ist wird genutzt
3. **SCAN LOS** — rote Taste → Scan laeuft, Live-Counter + ETA
4. **STOP** (gruene Taste) → Analyse laeuft, 30-60 s warten
5. **Report-Card** — Threat-Summary + Scroll fuer Details

### 6.2 Erste Reports auf den Laptop ziehen

```bash
scp -r pager:/root/loot/argus/reports/ ./reports/
```

Oder, komfortabler, via [argus-analyst](https://github.com/tschakram/argus-analyst):

```bash
git clone https://github.com/tschakram/argus-analyst.git
cd argus-analyst && pip install -r requirements.txt
cp config.example.json config.json  # SSH-Keys und Claude-API-Key eintragen
python report.py --full
```

---

## 7. Was jetzt?

- **Falsche Flaggen** bei eigenen Geraeten? → `/root/loot/argus/ignore_lists/mac_list.json`
- **Mudi WiFi faellt nach Reboot aus?** → siehe TROUBLESHOOTING.md
- **payload.sh exit 7?** → DuckyScript-Builtin-Fehler, siehe TROUBLESHOOTING.md
- **Pager-GUI (Port 1471) nicht erreichbar?** → SSH-Tunnel: `ssh -L 1471:localhost:1471 pager`
- **Scan laeuft, aber Report ist leer?** → `tools/rerun_analyser.py <session_id>`

---

## Related Projects

- [**argus-analyst**](https://github.com/tschakram/argus-analyst) — Desktop-App zur KI-Auswertung
- [**chasing-your-tail-pager**](https://github.com/tschakram/chasing-your-tail-pager) — als Submodul `cyt/`
- [**raypager**](https://github.com/tschakram/raypager) — als Submodul `raypager/`
