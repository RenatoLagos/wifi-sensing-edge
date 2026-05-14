# Positioning

## The thesis in one paragraph

WiFi sensing is undergoing the same transition that cloud compute went
through in 2006-2010. The science was proven by academic labs (MIT/Katabi)
and a generation of vertically integrated pioneers (Emerald Innovations,
Cognitive Systems, Origin AI) who built proprietary stacks because no
substrate existed. As of late 2025 the substrate exists: IEEE 802.11bf is a
ratified standard, open-source CSI foundation models are publicly trained
on billions of CSI samples, and the regulatory environment in the EU
structurally favors on-device architectures for ambient biometric data.
What the category needs next is a deployment layer that turns this
substrate into shipping product without rebuilding the radar, the model,
or the cloud from scratch. This repo is that deployment layer, beachheaded
in aging-in-place wellness monitoring because the sales cycle and unit
economics there match a focused team's build velocity.

## Why now: the three commoditization vectors

### 1. The hardware standard is settled

IEEE 802.11bf-2025 was published September 26, 2025. The amendment
specifically defines MAC and PHY modifications to enhance WLAN sensing in
license-exempt bands between 1 GHz and 7.125 GHz, and above 45 GHz. The
preamble of the standard explicitly lists target applications including
"user presence detection, environment monitoring in smart buildings, and
remote wellness monitoring." This is the exact use case this repo addresses.

What this means in practice:

- WiFi chipset vendors now have a target to implement against. Sensing-aware
  WiFi 7 chips will reach high volume over the next 2-3 years.
- A startup does not need to build proprietary radar to operate in this
  space — off-the-shelf 802.11 silicon is the platform.
- The ESP32-S3 is sufficient for the prototype. The production board can
  be cheaper, smaller, and lower power once dedicated 802.11bf parts are
  available.

### 2. The model layer is settled

Multiple foundation models for WiFi CSI are open-source as of November 2025:

- **WiFo-2** (Nov 2025) released the LH-CSI dataset: 11.6 billion CSI
  points, 78 subsets, designed as the substrate for cross-task fine-tuning.
- **AM-FM** trains on CSI-Bench, which provides 461 hours of in-the-wild
  CSI across 26 environments, 35 users, and 16 device types — explicitly
  built to evaluate cross-environment generalization, which is the central
  failure mode of bespoke CSI models.
- **Tiny-WiFo** (Nov 2025) demonstrates knowledge distillation of large
  CSI foundation models into lightweight student models specifically for
  edge deployment.
- **WiFo-CF** (Aug 2025) targets the related CSI feedback task and
  validates that the unified-FM approach generalizes across heterogeneous
  channel configurations.

A team starting in 2026 fine-tunes one of these on a vertical-specific
dataset; it does not pretrain a CSI foundation model. The same shift
happened in NLP between 2019 (everyone trained encoders) and 2022 (everyone
fine-tuned). The substrate for that shift in WiFi sensing is now available.

### 3. The regulatory environment rewards on-device

Two regulations matter for the EU market:

- **GDPR** (in force since 2018) requires data minimization: collect and
  retain only what is necessary for the stated purpose. Inference on raw
  biometric data is a high-friction operation under GDPR if the raw data
  is transmitted off-device. On-device inference is the cleanest posture.
- **EU AI Act**: general high-risk AI obligations apply from August 2,
  2026. Article 6(1), which governs AI embedded in CE-marked medical
  devices under MDR/IVDR, applies from August 2, 2027. (Note: as of April
  2026, EU Council and Parliament have signaled willingness to extend
  these deadlines to December 2027 and August 2028, but the regulation
  framework itself is locked in.) High-risk AI requires transparency,
  human oversight, post-market monitoring, technical documentation, and
  risk management — all materially easier to demonstrate when raw signals
  do not leave the device.

The on-device architecture is therefore not just faster and cheaper. It is
the architecture least exposed to GDPR and AI Act compliance risk. That is
a structural advantage for any team selling into European health and care
markets, where the rules are tightest.

## Our position in the category

The frame we use internally and externally: we are the deployment layer
that comes *after* the pioneers proved the science.

| Dimension | Vertically integrated pioneer (e.g. Emerald) | This project |
|-----------|----------------------------------------------|--------------|
| Hardware | Proprietary radar, ~$5k/unit | ESP32-S3 + Jetson Nano, ~$130 |
| Model | Bespoke per condition, trained in-house | Fine-tune of open foundation model |
| Inference location | Cloud / on-prem appliance | On-device, raw data never leaves |
| Deployment unit | Single-device per home | Mesh across rooms |
| Time to first install | Months (regulatory + custom hw) | Weeks (commodity hw + wellness framing) |
| Default first customer | Pharma sponsor in a clinical trial | Assisted living facility |

This is not a takedown of the pioneers. They proved the science, published
in Nature Medicine, and validated the category. They chose pharma because
pharma has the highest revenue per unit. The window for an infrastructure
play opens precisely because their unit economics keep them anchored in
pharma while a much larger consumer-and-facility market emerges underneath.

## Beachhead: aging-in-place wellness monitoring

### Why this market and not pharma RPM

Pharma trial RPM has structural mismatches with a startup at our stage:

- Sales cycle: 12-24 months from first contact to deployed pilot
- Customer concentration: small number of large pharma sponsors
- Regulatory entanglement: trial protocols, IRB review, validation studies
- Revenue timing: payment on milestones, often 6-12 months after pilot
  start

Aging-in-place wellness monitoring inverts every one of those:

- Sales cycle: 4-6 weeks from facility director conversation to pilot
- Customer fragmentation: thousands of independent facilities and home-care
  agencies
- Regulatory posture: wellness/safety monitoring, no medical claims, no
  FDA clearance needed for v1
- Revenue timing: monthly recurring billing direct to the facility

### Pricing model for v1 (no FDA)

Direct-to-facility wellness monitoring, billed monthly, no insurance
involvement. Pricing benchmarks for comparable safety/monitoring solutions
in assisted living sit in the $25-60/room/month range. Our target is
$30-50/room/month, sold as a bundle: hardware leased, software included,
remote support included.

### The Year 2 path: FDA 510(k) → CPT reimbursement

CMS reimbursement for remote patient monitoring under CPT 99453 (setup)
and 99454 (device supply for 30 days) requires the monitoring device to
be FDA-cleared as a medical device. Consumer wellness devices explicitly
do not qualify under current CMS guidance. The path to those codes is a
510(k) submission demonstrating substantial equivalence to a predicate
device, with timelines typically 6-18 months and budgets in the
$50k-$300k range.

The plan is therefore dual-track:

- **Track A (now, pre-FDA):** ship wellness monitoring to assisted living
  facilities. Generate revenue, references, and real-world deployment
  data. No medical claims, no FDA process.
- **Track B (months 6-18):** start the 510(k) process for the same
  hardware to unlock CPT reimbursement. The Track A revenue funds Track B.

Pharma trial RPM is an expansion story for Year 2-3, when we have a
fielded deployment base, real-world performance data, and (eventually) a
510(k) clearance to point at.

## Vision

The platform is an operating system for ambient perception in homes and
care environments. The same hardware and the same foundation model with a
different fine-tuning head address adjacent verticals:

- **Health and safety**: presence, breath rate, fall detection, motion
  patterns, tremor (beachhead)
- **Security**: occupancy and intrusion detection without cameras
- **Energy efficiency**: HVAC and lighting optimized to actual occupancy
- **Wellness**: sleep quality, activity patterns, social interaction

Health is first because the unit economics and urgency are clearest. The
broader thesis is that ambient perception becomes a default layer of the
built environment in the same way that connectivity did between 2005 and
2015.

## What we are not

We are explicitly not building:

- A consumer wearable
- A camera-based system (we are competing against cameras, not joining them)
- A cloud platform with raw biometric data as the moat
- A bespoke device for a single pharma sponsor

Saying these out loud matters because the design decisions only line up
when the anti-positioning is honest.
