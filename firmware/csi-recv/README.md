# csi-recv

Minimal ESP32-S3 CSI receiver. Associates with a WiFi AP, registers an
`esp_wifi_set_csi_rx_cb` callback, formats each CSI event as one CSV line
on UART0.

## Build & flash

```bash
. $HOME/esp/esp-idf/export.sh        # once per shell
idf.py set-target esp32s3            # once per project
idf.py menuconfig                    # set SSID + password under "wifi-sensing-edge"
idf.py build flash monitor
```

The serial console runs at **921600 baud** (raised from the default 115200
so CSI throughput is not console-bound).

## Output format

One line per received WiFi packet:

```
timestamp_us,rssi,channel,subcarrier_count,amp_0,phase_0,amp_1,phase_1,...\n
```

- `timestamp_us` — `esp_timer_get_time()` (microseconds since boot)
- `rssi` — `info->rx_ctrl.rssi` (dBm, negative)
- `channel` — `info->rx_ctrl.channel` (2.4 GHz channel number)
- `subcarrier_count` — `info->len / 2` (CSI buffer is pairs of int8)
- `amp_k`, `phase_k` — amplitude / phase from I/Q for subcarrier `k`

Identical to the format consumed by `jetson.ingest.parse_stream`.

## Wiring CSI events

To get CSI callbacks firing, the radio must be *receiving* packets. The
simplest setup is to associate with any 2.4 GHz access point in range
(home WiFi, phone hotspot) — once associated, the ESP32 receives
beacons and data frames continuously, and every received frame produces
a CSI event.

For a fully deterministic source, point a second ESP32 (future `csi-send`
project) on the same channel emitting at a fixed rate.

## CSI config

`esp_wifi_set_csi_config` is set to a sensible default for sensing:

```c
.lltf_en = true,         // legacy LTF (always present)
.htltf_en = true,        // 802.11n HT LTF
.stbc_htltf2_en = true,
.ltf_merge_en = true,    // merge HT LTF1/LTF2
.channel_filter_en = true,
.manu_scale = false,
```

Tune these in `main.c` only after you understand what each flag does — they
materially change the data layout. See `esp_wifi_types.h` in your ESP-IDF
install for the canonical definitions.
