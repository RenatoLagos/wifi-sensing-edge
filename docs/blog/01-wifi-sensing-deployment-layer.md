# WiFi sensing just commoditized. Here's the deployment layer.

*Draft v1 — May 14, 2026*

Emerald Innovations published in Nature Medicine. They proved that
WiFi-based RF sensing can do clinical-grade biometrics — breath rate,
sleep stages, gait, even Parkinson's tremor — without cameras, without
wearables, without the patient knowing the sensor is there. The science
is settled. So is the moat: bespoke radar, custom protocol stack, cloud
inference, single-device deployment, one model per condition. It worked.

In the past eighteen months, the substrate beneath that work changed
enough that a different kind of company is now possible. Not a better
version of Emerald. A different position in the same value chain. The
deployment layer.

This post is about why that window opened, what it looks like, and what
I'm building into it.

## The 2014-2024 era was an "invention" era

For the decade after Dina Katabi's group at MIT first showed WiFi-based
vital sign extraction, the people who built companies in this category
had to invent almost everything from the radio up:

- **Hardware**: off-the-shelf 802.11 silicon did not expose CSI in a way
  that supported clinical-grade sensing. You built proprietary radar.
- **Signal stack**: CSI extraction, denoising, motion isolation, breath
  isolation, gait reconstruction — published papers existed, but no
  standard pipeline did.
- **Models**: every condition (sleep, gait, tremor, fall) was its own
  small dataset, its own custom model, its own validation study. There
  was no foundation model to fine-tune. There was barely an ImageNet for
  CSI.
- **Deployment**: cloud inference was the default because the device
  could not run a sensible model. The "device" was the radar; the
  intelligence lived elsewhere.

This is what an *invention era* looks like: each company carries the
entire stack on its shoulders. The reward for surviving the invention
era is real — Emerald and the other pioneers did serious work and they
deserve the moats they built. But the cost is high: every customer
deployment is a research project, every new use case is a new model,
every regulatory submission is a custom argument.

In an invention era, the natural shape of a winning company is
**vertically integrated**. That is what Emerald is.

## Three things happened in the last eighteen months

### 1. IEEE 802.11bf-2025

On September 26, 2025, the IEEE published 802.11bf-2025, a standardized
amendment to 802.11 that defines MAC and PHY enhancements for WLAN
sensing in license-exempt bands between 1 GHz and 7.125 GHz, and above
45 GHz. The preamble of the standard lists target applications including
"user presence detection, environment monitoring in smart buildings, and
remote wellness monitoring."

This is not academic. WiFi chipset vendors now have an official target
to implement against. Sensing-aware WiFi 7 parts will reach volume over
2026-2028. You will not need to build a radar to operate in this
category. You will need to build everything *above* the radio.

### 2. CSI foundation models went public

For most of the post-AlexNet decade, training a "foundation model" for
WiFi CSI was a paper exercise. The datasets did not exist at scale, the
compute was not invested, the open-source culture was patchier than NLP
or vision.

In 2024 and 2025 that broke. Without trying to be exhaustive:

- **WiFo-2** (November 2025) released the LH-CSI dataset: 11.6 billion
  CSI points across 78 subsets, explicitly built as the substrate for
  cross-task fine-tuning.
- **AM-FM** was trained on CSI-Bench — 461 hours of in-the-wild CSI
  across 26 environments, 35 users, and 16 device types. The
  *cross-environment* generalization problem, which is the single
  hardest failure mode of bespoke CSI models, has a public benchmark.
- **Tiny-WiFo** (November 2025) demonstrated knowledge distillation of
  large CSI foundation models into student models small enough to run
  on the kinds of NPUs you will find in an ambient sensor.
- **WiFo-CF** (August 2025) showed that the unified-foundation-model
  approach handles heterogeneous channel feedback configurations,
  which is exactly the problem you have when you deploy across a fleet
  of mixed hardware.

A team starting in 2026 does not pretrain a CSI foundation model. It
fine-tunes one of these on a vertical-specific dataset. The same shift
happened in NLP between 2019 and 2022 — and the companies that thrived
on the back side of that shift were not the people who trained the
biggest models. They were the people who shipped products on top.

### 3. The regulatory environment rewards on-device inference

Two regulations matter:

- **GDPR**, in force since 2018, requires data minimization. Streaming
  raw biometric signals across a border is a high-friction operation.
  Performing inference on-device and emitting only the prediction is
  not.
- The **EU AI Act**'s general high-risk obligations apply from
  August 2, 2026. The medical-device-specific Article 6(1) applies from
  August 2, 2027 (with possible extensions under discussion). The Act
  requires transparency, human oversight, post-market monitoring,
  technical documentation, risk management. Every one of those is
  materially easier to demonstrate when only the prediction leaves the
  device.

This is not a loophole. The AI Act has no clause that says "on-device
inference exempts you" — it does not exist. But the *cost* of
compliance is structurally lower for an on-device architecture, and the
trust position with a hospital, a care facility, or a privacy regulator
is structurally stronger. Edge inference is not a performance
optimization any more. It is a regulatory and trust posture.

## Why this resembles 2006 cloud

In 2006, the invention era of internet infrastructure had been underway
for a decade. Big companies had built custom datacenters. Smaller
companies built smaller custom datacenters and hated every minute of it.
AWS launched and made the question "do we run our own infrastructure?"
the wrong question for ninety percent of new companies.

That is not because Amazon was better at servers than anyone else. It
was because the *substrate* was ready: x86 commoditization, Linux,
virtualization, internet bandwidth. The thing AWS did was assemble that
substrate into a deployment layer that a new company could ship product
on without having to invent any of it.

WiFi sensing is at the same kind of inflection. The substrate is now
in place. The deployment layer is the next position in the category.

A deployment-layer company in WiFi sensing looks like:

- **Commodity hardware**, not custom radar. An ESP32-S3 with an
  external antenna costs about thirty dollars and exposes CSI through
  `esp-csi`. A Jetson Nano runs the inference. The whole sensor is
  about a hundred and thirty dollars of off-the-shelf parts. Production
  units shrink further once 802.11bf chipsets are volume.
- **Foundation models, not bespoke training**. You fine-tune one of
  WiFo-2, AM-FM, or Tiny-WiFo for your vertical, you do not pretrain.
  You collect a small per-task dataset and let the substrate carry the
  generalization. You distill the result to a model the edge device can
  actually run.
- **Edge inference as the default**. Raw CSI never leaves the room.
  Predictions cross the boundary. The deployment is GDPR-clean by
  construction, AI Act-friendly by construction, and customer-trust
  friendly by construction.
- **Multi-room mesh**, not single-device. A real care environment has
  more than one room. The deployment unit is "a facility" or "a home,"
  not "a device."

## What this means for the first market

The pioneers anchored in pharma trial RPM because pharma sponsors will
pay six figures per device per study to validate a biomarker. The unit
economics worked for vertical integration. The sales cycle - twelve to
twenty-four months from first contact to deployed pilot - was tolerable
because the deal size justified it.

A deployment-layer company cannot wait twenty-four months for its first
customer. The natural first market is the one that has been *waiting* for
this technology to commoditize: aging-in-place. Assisted living
facilities, home care agencies, senior living. Sold as wellness and
safety monitoring, not as a medical device. Priced per room per month.
Sales cycles measured in weeks. The reimbursement-grade version, billed
through CPT 99453/99454 RPM codes, comes later — after a 510(k)
clearance — and that is the year-two unlock.

Pharma trial RPM is still a real market. It is just a year-two or
year-three expansion target, not a year-one wedge. By the time we get
there, we have a fielded deployment base and a foundation model
fine-tuned on real cross-site data — the things you cannot buy and you
cannot fake.

## What I am building

I am building exactly this deployment layer. ESP32-S3 plus Jetson Nano,
with the model and pipeline shaped so that the architecture migrates to
an integrated 802.11bf-aware unit when the silicon arrives.

The repo today proves the baseline in the honest order it should be
proved: first the ingest contract, then the synthetic end-to-end
pipeline, then the classical estimators, then real hardware validation,
and only after that learned deployment models. The first detection target
is breath rate; the classical FFT baseline already recovers eighteen
breaths per minute from synthetic CSI with zero error and a
peak-to-median SNR ratio of about seven thousand. Real CSI capture and
parser validation remain the next hardware-gated milestone.

The repo is open and the docs are honest:
[github.com/RenatoLagos/wifi-sensing-edge](https://github.com/RenatoLagos/wifi-sensing-edge).
I publish status, code, and benchmarks as they happen. The bench numbers
that go in this post will be replaced with measured ones when measured
ones exist.

## What I do not know yet

I do not know how badly cross-environment domain gap will bite on real
CSI in real assisted living facilities. The foundation-model approach
should help, but every previous generation of CSI models cratered when
moved between rooms. This is the central engineering risk.

I do not know whether the right business motion is direct-to-facility or
through care platforms that already have facility distribution. I expect
to be wrong about this and to correct after the first ten conversations.

I do not know what an 802.11bf-aware WiFi 7 chip in 2027 will actually
cost the way I will buy it. I am building so that the answer does not
change the architecture, only the bill of materials.

The thesis is the deployment layer. The execution is the test.

---

*If you are working on something adjacent — RF sensing, edge AI for
healthcare, ambient computing in care settings — I want to talk.
[X: @RenatoLagos](https://x.com/RenatoLagos)*
