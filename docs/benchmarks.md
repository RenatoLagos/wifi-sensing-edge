# Benchmarks

Template for tracking edge inference performance on the Jetson Nano.

**Numbers here become evidence in the YC application, EIC pitch, and Bayer G4A
submission. Honest measurement matters more than impressive numbers.**

## Targets (from architecture doc)

| Metric | Target |
|--------|--------|
| End-to-end latency (ESP32 RX -> output) | < 100 ms |
| Inference latency (TRT FP16) | < 50 ms |
| Throughput (sustained) | >= 10 Hz |
| Idle power | < 5 W |
| Inference power | < 10 W |
| Model size on disk | < 50 MB |

## Measurements

All measurements: fill in when you have real numbers. Do not predict.

### Presence detection (binary classifier)

| Metric | PyTorch eager | ONNX Runtime | TensorRT FP16 | TensorRT INT8 |
|--------|---------------|--------------|---------------|---------------|
| Latency p50 (ms)   | TBD | TBD | TBD | TBD |
| Latency p99 (ms)   | TBD | TBD | TBD | TBD |
| Throughput (Hz)    | TBD | TBD | TBD | TBD |
| Accuracy (in-domain)  | TBD | TBD | TBD | TBD |
| Accuracy (cross-env)  | TBD | TBD | TBD | TBD |
| Engine size (MB)   | n/a | TBD | TBD | TBD |

### Breath rate estimation

| Metric | PyTorch eager | TensorRT FP16 |
|--------|---------------|---------------|
| Latency p50 (ms) | TBD | TBD |
| MAE vs. ground truth (bpm) | TBD | TBD |
| Throughput (samples / s)   | TBD | TBD |

### Tremor detection (Parkinson's wedge — Aug-Sep)

| Metric | Value |
|--------|-------|
| Latency p50 (ms) | TBD |
| Sensitivity (true positive rate) | TBD |
| Specificity (true negative rate) | TBD |
| MAE vs. accelerometer reference (Hz) | TBD |

## Methodology

For every row above, record:

- **Date** of measurement
- **Git commit** at which the measurement was taken
- **Hardware**: ESP32 board rev, antenna, Jetson SKU, JetPack version
- **Software**: ESP-IDF version, PyTorch / TRT / CUDA versions
- **Dataset**: train/eval split, number of samples, source
- **Conditions**: room dimensions, RF environment, channel

If any of those move, re-measure. The benchmarks table is **never** a
historical aggregate — it always reflects the latest commit.

## Power measurement

Use `tegrastats` for live power readings on the Jetson:

```bash
sudo tegrastats --interval 200 | tee tegrastats.log
```

Sustained inference power = average over a 60-second window with the
pipeline running on a fixed input stream.
