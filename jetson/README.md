# jetson/

Edge runtime for the NVIDIA Jetson Nano: CSI ingest, preprocessing,
and TensorRT inference.

## Why edge

Three reasons, in order of importance for the pharma wedge:

1. **Privacy**: raw CSI never leaves the device. No cloud, no PHI in flight.
2. **Latency**: end-to-end ESP32 → Jetson → output target <100ms.
3. **Cost**: $130 of hardware vs. $5k/patient wearable studies.

## Stack

- JetPack 4.6.x (do NOT auto-upgrade — clone the SD card first)
- PyTorch 1.10-1.12 (matches JetPack 4.6 CUDA 10.2)
- TensorRT 8.2 (bundled with JetPack 4.6)
- ONNX Runtime 1.11 (for non-TRT fallback)

Models are trained on a desktop GPU or Colab, exported to ONNX, then
optimized to TensorRT FP16 engines for deployment. **The Nano does not
train.**

## Layout (to be created)

```
ingest/      CSI receiver (UART or UDP) -> ring buffer
preprocess/  Filtering, denoising, feature extraction (NumPy / cuSignal)
inference/   TensorRT engine wrappers
pipeline/    asyncio orchestration: ingest -> preprocess -> infer -> emit
bench/       Latency, FPS, power consumption benchmarks
```

## Setup (placeholder — fill in when verifying Jetson)

```bash
# Check JetPack version FIRST — do not upgrade if it works
cat /etc/nv_tegra_release

# Set up Python env
python3 -m venv ~/venvs/wse
source ~/venvs/wse/bin/activate

# PyTorch for JetPack 4.6 (NVIDIA prebuilt wheel)
# See: https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048
```
