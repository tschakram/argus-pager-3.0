# CONTINUE.md — argus-pager 3.0

Diese Datei bringt einen frischen Chat in Sekunden auf Stand.
**Zuerst lesen, bevor du Code anfasst.**

---

## Projekt

Counter-Surveillance auf dem **WiFi Pineapple Pager**. Erkennt verdächtige
WiFi-/BT-Geräte, IMSI-Catcher und Silent-SMS während man sich bewegt.

Fork von `argus-pager-2.0` (`origin/main` HEAD `3eaf126`), rebrand als
`argus-pager-3.0`. Codebasis vorerst identisch zu 2.0; Mudi-7-Support
und Pager-Firmware-2.0-Anpassungen kommen schrittweise.

---

## Aktueller Stand (2026-11-01)

- Repo: `github.com/tschakram/argus-pager-3.0`
- **HEAD: initial 3.0.0-alpha0** (Rebrand-Commit)
- Submodule `cyt/` → `chasing-your-tail-pager@ec141b1` (main)
- Submodule `raypager/` → `raypager@fa3114b` (master)
- Pager-Hardware: **Factory Reset + Firmware-Upgrade auf 2.0** am Pineapple Pager (Upgrade läuft)
- Mudi-IP neu: **172.16.0.1** (war 192.168.8.1, Router-Konflikt-Fix)

---

## Hardware-Kompatibilität

| Komponente | Modell | Status |
|---|---|---|
| Pager | WiFi Pineapple Pager (OpenWrt 24.10.1, Firmware **2.0**) | Deploy noch nicht möglich — Upgrade läuft |
| Mudi V2 | GL-iNet GL-E750V2 (4G LTE, Quectel-Modem) | aus 2.0 übernommen, läuft |
| Mudi 7 | GL-iNet GL-E5800 (5G) | **neu in 3.0** — Code-Pfade noch zu ergänzen |
| GPS | u-blox M8130 USB-Dongle, `/dev/ttyACM0` @ 4800 baud | übernommen |

---

## Nächste Arbeit (vorgeschlagen)

### Task 1: Mudi-Auto-Detection
Script auf dem Mudi, das anhand `/tmp/sysinfo/model` oder
`/proc/device-tree/model` zwischen E750V2 und E5800 unterscheidet
und modell-spezifische Pfade (AT-Device, `gl_modem`-Variante,
GPS-Device) setzt. Ablage: `raypager/python/mudi_detect.py`.

### Task 2: Mudi-7-AT-Pfade
Beim E5800 (5G) heißt das AT-Device nicht zwingend
`/dev/mhi_QMI0`/`/dev/ttyUSB2` wie beim E750V2. Erst Hardware
checken, dann `cell_info.py` abstrahieren.

### Task 3: Pager-Firmware-2.0 Framework-Diff
Nach Pager-Upgrade: alle Framework-Builtins (`LOG`, `NUMBER_PICKER`,
`SHOW_REPORT`, `LED`, `WIFI_PCAP_*`, `PINEAPPLE_HOPPING_*`) gegen
`payload.sh` validieren. Breaking Changes dokumentieren.

### Task 4: argus-analyst anbinden
`argus-analyst` (Desktop-App, Claude-API) soll Reports aus
`/root/loot/argus/reports/` ziehen und visualisieren. Verbindung
zur neuen Mudi-IP `172.16.0.1` in `argus-analyst/config.example.json`
übernehmen.

---

## OPSEC-Grundregeln

- Platzhalter-OUIs in Beispielen/Tests: `aa:bb:cc:dd:ee`, `11:22:33:44:55:66`, `bb:cc:dd:ee:ff`, `cc:dd:ee:ff:aa`, `ca:fe:ca:fe`, `de:ad:be:ef`, `bc:bc:bc:bc:bc:bc`, `01:02:03:04:05:06`, `00:00:00:00:00:00`, `ff:ff:ff:ff:ff:ff`.
- Keine echten MACs, GPS-Koordinaten, IMEI, IMSI, SSIDs der Umgebung oder API-Keys im Repo.
- `hooks/pre-commit` (via `git config core.hooksPath hooks`) blockiert alle Verstöße.
- `config.json`, `watch_list.json`, `ignore_lists/*.json` (ohne `.example`) sind gitignored.
- Reports, PCAPs, GPS-Tracks werden **nie** committed.

---

## Related Repos

- [**argus-analyst**](https://github.com/tschakram/argus-analyst) — Desktop-App, KI-Auswertung
- [**chasing-your-tail-pager**](https://github.com/tschakram/chasing-your-tail-pager) — als `cyt/` Submodul
- [**raypager**](https://github.com/tschakram/raypager) — als `raypager/` Submodul
- [**argus-pager-2.0**](https://github.com/tschakram/argus-pager-2.0) — Vorgänger (Fork-Quelle)
- [**argus-pager**](https://github.com/tschakram/argus-pager) — 1.x (archivtauglich)
