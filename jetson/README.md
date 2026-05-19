# jetson/

Edge runtime for the NVIDIA Jetson Nano: CSI ingest, preprocessing, and
local result emission. Today this directory is a **classical-signal baseline**
plus a runnable demo pipeline. TensorRT model serving is planned, not yet
implemented in this repo.

## What is real today

- `ingest/` parses the ESP32 CSV wire format into `CSIFrame` objects.
- `preprocess/` contains two working baselines:
  - `breath_rate.py` - FFT-based breath-rate estimation
  - `motion.py` - variance-based idle / presence / movement classification
- `pipeline/` wires ingest + preprocess + emitters into a runnable loop.
- `scripts/demo_pipeline.py` exercises the full path with synthetic CSI.

## Why edge

Three reasons, in order of importance for the current senior-care wedge:

1. **Privacy**: raw CSI never leaves the device.
2. **Latency**: end-to-end ESP32 -> Jetson -> output target <100 ms.
3. **Cost**: commodity hardware is cheap enough to deploy room by room.

## Current stack

- Python 3.10+
- NumPy / SciPy for the signal-processing baseline
- Rich for the live terminal dashboard

This is enough to validate the ingest contract, windowing logic, and baseline
estimators before real hardware or ML deployment are introduced.

## Planned deployment stack

- JetPack 4.6.x on Jetson Nano
- PyTorch on desktop/Colab for training
- ONNX -> TensorRT FP16 on the Nano for deployment

That path is architectural intent, not current implementation. The Nano does
not train models; it is the inference target once a compact model exists.

## Layout

```
ingest/      CSV receiver and parser for CSI frames
preprocess/  Classical signal baselines used today
pipeline/    Windowing, orchestration, and emitters
```

`inference/` and `bench/` are intentionally absent for now. They become real
once the project moves from baseline validation to deployed model serving.

## Jetson setup

```bash
# Check JetPack version FIRST - do not upgrade blindly
cat /etc/nv_tegra_release

# Set up Python env
python3 -m venv ~/venvs/wse
source ~/venvs/wse/bin/activate

# Install repo dependencies
pip install -r requirements.txt
```

If the target is a real Nano later, pin package versions against the installed
JetPack release before adding CUDA, PyTorch, or TensorRT-specific steps.
