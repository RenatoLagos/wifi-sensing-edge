# firmware/

ESP32-S3 firmware for CSI capture, built with ESP-IDF + [esp-csi](https://github.com/espressif/esp-csi).

## Layout (to be created when hardware arrives)

```
csi-recv/    Receiver firmware: subscribes to CSI callbacks, streams over UART/UDP
csi-send/    Companion sender firmware (optional): emits known training packets
common/      Shared headers, config, channel definitions
```

## Build

```bash
# Set up ESP-IDF v5.1+ first (https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/get-started/)
. $HOME/esp/esp-idf/export.sh

cd firmware/csi-recv
idf.py set-target esp32s3
idf.py build flash monitor
```

## Hardware notes

- ESP32-S3-DevKitC with external u.FL→SMA 2.4GHz antenna (better SNR than PCB antenna).
- USB-C cable rated for data (not power-only) — cheap cables silently break flashing.
- Use channel 6 by default (2.437 GHz) to minimize interference in 2.4 band.

## Streaming protocol (initial)

UART at 115200 baud, line-delimited CSV:

```
timestamp_us,rssi,channel,subcarrier_count,csi_amp_0,csi_phase_0,...
```

Once stable, switch to binary frames over UDP for higher throughput.
