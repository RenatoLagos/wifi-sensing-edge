# wifi-sensing-edge

Ambient electromagnetic perception for pharma trial RPM.
Edge inference on $130 of hardware. No cameras. No cloud. No wearables.

## What this is

A WiFi CSI (Channel State Information) sensing platform that runs inference
**on-device** on a Jetson Nano, fed by ESP32-S3 RF frontends. Target use case:
passive digital biomarkers (presence, respiration rate, motion patterns,
tremor) for pharma clinical trial remote patient monitoring.

## Architecture

```
ESP32-S3 (RF frontend, CSI capture via esp-csi)
    | UART 115200 / WiFi UDP
    v
Jetson Nano (preprocessing + TensorRT inference)
    | MQTT / WebSocket / local display
    v
Output (latency target: <100ms end-to-end)
```

## Status

| Component | State |
|-----------|-------|
| Repo scaffold | Day 1 (2026-05-14) |
| ESP32 firmware | Pending hardware arrival |
| Jetson edge runtime | Pending JetPack verification |
| Presence detection | Not started |
| Breath rate detection | Not started |
| Tremor detection | Not started |
| Foundation model embryo | Not started |

## Hardware

- ESP32-S3-DevKitC ×2 (RF frontend)
- u.FL → SMA 2.4 GHz antennas ×2
- NVIDIA Jetson Nano 4GB (edge inference)
- MicroSD 32GB

Total: ~$130 USD.

## Software

- Firmware: ESP-IDF + [esp-csi](https://github.com/espressif/esp-csi)
- Training: PyTorch on desktop/Colab (Jetson Nano cannot train large models)
- Deployment: ONNX → TensorRT FP16 on Jetson
- Pipeline: Python asyncio for streaming CSI ESP32 → Jetson → output

## Repo layout

```
firmware/   ESP32 firmware (ESP-IDF projects)
jetson/     Jetson edge runtime (PyTorch / TensorRT inference)
notebooks/  Jupyter notebooks for CSI analysis and model R&D
docs/       Architecture, design notes, eval reports
scripts/    Utility scripts (data capture, conversion, benchmarks)
data/       Raw CSI captures (gitignored)
```

## Reproducibility

Every demo in this repo includes:
- Exact hardware used
- Software versions (ESP-IDF, JetPack, PyTorch, TensorRT)
- Data capture procedure
- Replication steps

Honesty about what works and what doesn't is the point.

## License

MIT — see [LICENSE](LICENSE).
