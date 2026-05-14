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
becomes a sensing-aware 802.11bf WiFi 7 chipset (the standard was ratified
in September 2025, silicon volume is ramping over 2026-2028), and the
"Jetson" becomes an embedded SoC with NPU. The boundary stays the same;
both halves get smaller, cheaper, and lower-power without touching the
ingest/preprocess/inference contract on either side.

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

## Model approach: fine-tune, do not pretrain

A CSI foundation model trained from scratch needs millions of dollars of
compute and access to multi-site CSI at a scale a startup cannot collect
in Year 1. Public foundation models published in 2024-2025 — WiFo-2,
AM-FM, Tiny-WiFo, WiFo-CF — collapse that problem into a fine-tuning
exercise. Our path:

1. Start from a published, open-source CSI foundation model checkpoint.
2. Fine-tune on a task-specific head (presence, breath rate, fall, tremor)
   with a small per-task dataset captured in our target environments.
3. Knowledge-distill into a small student model sized for the Nano's
   memory and latency budget (Tiny-WiFo's approach is directly applicable).
4. Export ONNX, build a TensorRT engine, deploy.

The classical signal-processing baseline (e.g. `jetson/preprocess/breath_rate`)
remains in the pipeline as a regression target. Any learned model that does
not beat the FFT-based baseline on both accuracy and latency is not shipped.

## Why edge inference is the architecture, not an optimization

There is a meaningful regulatory and trust reason on top of the latency and
cost arguments:

- **GDPR data minimization** (since 2018) makes any cross-border transmission
  of raw biometric signals a compliance-heavy operation. Keeping raw CSI on
  the device eliminates the data-flow surface entirely.
- **EU AI Act** high-risk obligations (general from August 2026,
  medical-device-specific from August 2027) require transparency, human
  oversight, and post-market monitoring. All three are materially easier
  to demonstrate when the only thing crossing the device boundary is a
  prediction, not a raw sensor stream.

This is why "inference at the edge" appears as a top-level architectural
constraint and not as a deployment optimization to be relaxed later.

## Where this becomes a product

The current architecture is the **research prototype**. The product version is:

- A single integrated unit: an 802.11bf-aware WiFi 7 chipset paired with
  an embedded NPU SoC, packaged for unobtrusive room install
- A shared CSI foundation model fine-tuned per facility with on-device
  adaptation, so cross-environment generalization is solved without
  retraining centrally
- A privacy-preserving update channel: model weights flow down, only
  aggregated evaluation metrics (never raw CSI) flow up
- Integrations with assisted-living and home-care platforms (EHR-lite,
  alert routing, nurse-call systems) as the first integration surface
- Pharma trial RPM as a Year 2-3 expansion target, once a fielded
  deployment base and an FDA 510(k) clearance support that claim

Until then: ESP32-S3 + Jetson Nano is the cheapest path to credible signal.
See [positioning.md](positioning.md) for the full market thesis.
