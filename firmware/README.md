# firmware/

ESP32-S3 firmware for CSI capture. Built with ESP-IDF v5.1+.

## Projects

| Project | Purpose |
|---------|---------|
| `csi-recv/` | Associates with an access point, registers a CSI receive callback, streams one CSV line per CSI event to UART. |

A future `csi-send/` project (companion emitter) can be added when we need a
deterministic packet source. For first capture the home AP or a phone hotspot
is sufficient.

## One-time ESP-IDF setup

```bash
# Linux / WSL
mkdir -p ~/esp && cd ~/esp
git clone -b release/v5.1 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf
./install.sh esp32s3
```

Each new shell session:

```bash
. $HOME/esp/esp-idf/export.sh
```

## Per-project flow

```bash
cd firmware/csi-recv
idf.py set-target esp32s3
idf.py menuconfig            # set wifi credentials under "wifi-sensing-edge"
idf.py build flash monitor   # builds, flashes, opens serial monitor
```

Monitor at 921600 baud. Output is line-delimited CSV in the format defined
in [docs/architecture.md](../docs/architecture.md):

```
timestamp_us,rssi,channel,subcarrier_count,amp_0,phase_0,amp_1,phase_1,...
```

The same lines feed `jetson.ingest.parse_stream` unchanged.

## Hardware reminders

- ESP32-S3-DevKitC-1 N16R8 (8 MB PSRAM, 16 MB flash, u.FL connector)
- External u.FL -> SMA antenna (the on-PCB antenna SNR is unusable for CSI)
- USB-C data-rated cable (not power-only — cheap cables silently break flashing)

## Limitations of this scaffold

Written without hardware in hand, May 14, 2026. Compiles against the
ESP-IDF v5.1 API; minor tweaks likely on first real flash. The code path
intentionally prefers clarity over performance — `printf` in the CSI
callback adds latency on the WiFi RX path. The first production iteration
will move emission to a dedicated task pulling from a ring buffer.
