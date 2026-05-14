# notebooks/

Jupyter notebooks for CSI exploration, model R&D, and writeups for the repo.

## Convention

Every notebook in this directory follows the pattern:

```
NN_short-slug.ipynb
```

Where `NN` is a two-digit ordinal. Notebooks tell a story in order; read them
top-to-bottom to trace how the prototype evolved.

| Notebook | Purpose |
|----------|---------|
| `01_csi_first_capture.ipynb` | First raw CSI capture, sanity plots, sensor noise floor |
| `02_presence_detection.ipynb` | Binary classifier: human in room yes/no |
| `03_breath_rate.ipynb` | FFT on CSI amplitude, find peak in 0.1-0.3 Hz |
| `04_fall_detection.ipynb` | Time-series classifier on CSI motion signatures |
| `05_cross_environment.ipynb` | Same model evaluated across rooms — domain gap |
| `06_tremor_simulation.ipynb` | Parkinson's tremor wedge — controlled tremor capture |

Notebooks live in this repo for transparency. They are NOT the production
path — production code lives in `jetson/` and runs on-device.

## Reproducibility

Each notebook should declare at the top:

- Hardware used (ESP32 board rev, antenna, Jetson model)
- Software versions (ESP-IDF, JetPack, PyTorch)
- Data source (relative path under `data/`)
- Expected runtime on the target hardware

A reader with the same hardware should be able to re-run any notebook.
