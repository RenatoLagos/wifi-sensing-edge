# wifi-sensing-edge

> Ambient perception infrastructure for senior care.
> Edge inference on ~$130 of off-the-shelf hardware. No cameras. No cloud. No wearables.

## What this is

A WiFi CSI (Channel State Information) sensing platform that runs inference on-device on a Jetson Nano, fed by ESP32-S3 RF frontends. Target use case: **passive presence, breath rate, motion, and fall detection** for assisted living facilities, home care, and aging-in-place — without cameras, wearables, or raw RF data leaving the room.

## Why now (May 2026)

WiFi sensing just commoditized. Three structural shifts make this the right window for an infrastructure play:

- **IEEE 802.11bf-2025** ratified September 26, 2025. WLAN sensing is now a native amendment to 802.11, with explicit target applications including "user presence detection, environment monitoring in smart buildings, and remote wellness monitoring." Sensing is no longer a research curiosity — it is a standard layer of the WiFi stack.
- **Open-source CSI foundation models** matured in 2024-2025. WiFo-2 (Nov 2025) released the LH-CSI dataset of 11.6 billion CSI points across 78 subsets. AM-FM trained on CSI-Bench (461 hours, 26 environments, 35 users, 16 device types). Tiny-WiFo (Nov 2025) demonstrated knowledge distillation specifically for edge deployment. The substrate for fine-tuning instead of training-from-scratch is real and available.
- **GDPR data minimization** (in force since 2018) and the **EU AI Act** (general high-risk obligations from August 2026, medical-device-specific from August 2027) make architectures where raw biometric signals never leave the device materially easier to ship into EU healthcare and care facilities. On-device inference is no longer a performance optimization — it is a regulatory posture.

The science of RF biosensing was proven by Dina Katabi's group at MIT and commercialized by Emerald Innovations for pharma trials. The category now needs a deployment layer that:

1. Uses commodity hardware (~$130) instead of proprietary radar (~$5k/unit)
2. Fine-tunes a shared foundation model cross-site instead of training one bespoke model per disease per environment
3. Runs inference locally so raw RF data never leaves the room
4. Meshes across multiple rooms instead of being a single-device deployment

That deployment layer is what this repo is.

## Beachhead: aging-in-place wellness monitoring

Pharma trial RPM has 12-24 month sales cycles. Useful for Year 2-3 expansion; incompatible with the build velocity we need now.

The first market is **assisted living facilities, home care, and senior living**, sold as wellness and safety monitoring (no medical claims, no FDA clearance required for v1). The same hardware and software stack carries over later to FDA 510(k) clearance, which unlocks CMS reimbursement under CPT 99453/99454 RPM codes — but those codes structurally require an FDA-cleared device and are a Year 2 milestone, not a Day 1 claim.

## Architecture

```
+------------------+        UART 115200       +-----------------------+
| ESP32-S3-DevKitC | -----------------------> |   Jetson Nano (4GB)   |
| u.FL -> SMA ant. |   (or WiFi UDP later)    |   JetPack 4.6.x       |
| ESP-IDF + esp-csi|                          |   PyTorch -> TensorRT |
+------------------+                          +-----------------------+
                                                         |
                                                         v
                                                +-----------------+
                                                |  Local emit:    |
                                                |  MQTT, screen,  |
                                                |  log, alert     |
                                                +-----------------+
```

End-to-end latency target: **<100 ms** from packet RX to prediction emitted.
Full detail in [docs/architecture.md](docs/architecture.md).

## Status

| Component                                | State                                                                                  |
| ---------------------------------------- | -------------------------------------------------------------------------------------- |
| Repo scaffold                            | Done (May 14, 2026)                                                                    |
| CSI ingest module                        | Done — `jetson/ingest/`                                                                |
| Synthetic CSI simulator                  | Done — `scripts/csi_simulator.py`                                                      |
| Breath rate estimator (classical FFT)    | Working on synthetic — recovers 18.00 bpm with zero error, 7000× peak/median vs idle  |
| Test suite                               | 11/11 passing                                                                          |
| ESP32 firmware                           | Pending hardware arrival                                                               |
| Real CSI capture + parser validation     | Pending hardware arrival                                                               |
| Foundation model fine-tune (Tiny-WiFo)   | Backlog                                                                                |
| Fall detection                           | Backlog                                                                                |
| Multi-room mesh                          | Backlog                                                                                |
| FDA 510(k) prep                          | Year 2                                                                                 |

## Vision

Long term: an operating system for ambient perception in homes and care environments. Senior care first because the unit economics and sales cycle align with what a focused team can ship. Health-adjacent verticals (security, energy efficiency, occupancy analytics) reuse the same hardware and the same foundation model with a different fine-tuning head. Pharma trial RPM is an expansion story for Year 2-3.

## Repo layout

```
firmware/   ESP32 firmware (ESP-IDF projects)
jetson/     Jetson edge runtime (ingest, preprocess, inference, pipeline, bench)
notebooks/  Jupyter notebooks for CSI analysis and model R&D
docs/       Architecture, positioning, hardware BOM, eval reports
scripts/    Utilities (CSI simulator, demo runners, conversion)
data/       Raw CSI captures (gitignored)
models/     Checkpoints and TensorRT exports (gitignored)
tests/      pytest suite
```

## Reproducibility

The `jetson/` runtime ships with pinned dependencies and a `scripts/csi_simulator.py` so you can validate the full pipeline (ingest → preprocess → inference → emit) without hardware. The synthetic simulator emits CSI packets statistically matched to the real ESP32 output, so the breath-rate / presence pipelines can be developed end-to-end before the radios arrive.

```bash
# On Jetson (or any Linux box with Python 3.11+):
cd jetson
pip install -r requirements.txt
python -m pytest                              # 11/11
python scripts/csi_simulator.py --bpm 18 | python jetson/pipeline/runner.py
```

## Portfolio

Featured in my portfolio under **Backend · Edge ML · AI Engineering** — see [renatolagos.com](https://renatolagos.com) and the marketing site at [renatolagos-site.vercel.app](https://renatolagos-site.vercel.app).

---

**Author**: Renato Lagos · [renatolagos.com](https://renatolagos.com) · Backend / Edge ML / AI Engineer · Berlin
