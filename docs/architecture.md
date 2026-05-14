# Architecture

## High level

```
+------------------+        UART 115200       +-----------------------+
| ESP32-S3-DevKitC | -----------------------> |   Jetson Nano (4GB)   |
| u.FL -> SMA ant. |   (or WiFi UDP later)    |   JetPack 4.6.x       |
| ESP-IDF + esp-csi|                          |   PyTorch -> TensorRT |
+------------------+                          +-----------------------+
                                                         |
                                                         | MQTT / WebSocket
                                                         v
                                                +-----------------+
                                                |   Demo output   |
                                                |  (local screen, |
                                                |   dashboard, or |
                                                |   log file)     |
                                                +-----------------+
```

## Why this split

The ESP32-S3 is doing one thing: **RF capture**. It owns the radio,
extracts CSI via `esp-csi`, and streams. Cheap, deterministic, embedded.

The Jetson Nano is doing the **inference work**: preprocessing CSI tensors,
running a TensorRT engine, emitting predictions. It has the CUDA, the RAM
and the toolchain. The ESP32 does not.

This split is also the productionable split: in a deployed system the ESP32
would become a custom RF board (smaller, cheaper, lower-power) and the
"Jetson" would become an embedded SoC with NPU. The boundary stays the same.

## Data flow

1. ESP32 receives a WiFi packet on channel 6 (2.437 GHz).
2. `esp-csi` callback fires with the CSI tensor for that packet.
3. Firmware serializes timestamp + RSSI + CSI subcarriers to UART.
4. Jetson `ingest/` reads UART, parses, pushes to a ring buffer.
5. `preprocess/` consumes the buffer, applies filters (Hampel for outliers,
   bandpass for the band of interest), extracts features.
6. `inference/` runs the TensorRT engine on the feature tensor.
7. `pipeline/` emits the prediction over MQTT / WebSocket / local log.

## Latency budget

End-to-end target: **<100 ms** from packet RX to prediction emitted.

| Stage           | Budget   |
|-----------------|----------|
| ESP32 CSI -> UART | 5 ms   |
| UART transit   | 10 ms    |
| Jetson parse    | 5 ms    |
| Preprocess      | 20 ms    |
| Inference (TRT FP16) | 50 ms |
| Emit            | 10 ms    |
| **Total**       | **100 ms** |

These are targets, not measurements. Real numbers go in `jetson/bench/`
when we have them.

## Why TensorRT not raw PyTorch

The Nano can run PyTorch but it leaves 3-5x performance on the table.
TensorRT FP16 with engine caching and INT8 quantization (where it doesn't
hurt accuracy) is the difference between "demo on the bench" and "deployed
sensor". Same model, same accuracy target, very different latency.

## Where this becomes a product

The current architecture is the **research prototype**. The product version is:

- A single custom board with an ESP32-class RF frontend and an SoC with NPU
- A foundation model fine-tuned on multi-site CSI for cross-environment
  generalization
- A privacy-preserving update channel (so the model can be improved without
  sending raw CSI anywhere)
- Integrations with pharma trial RPM platforms

Until then: ESP32-S3 + Jetson Nano is the cheapest path to credible signal.
