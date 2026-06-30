# WiFi sensing just commoditized. The bottleneck is deployment.

*Revised draft - May 21, 2026*

Most people still talk about WiFi sensing like the hard part is proving the science.
It is not.

The science was proven years ago.
MIT's work and the first commercial pioneers already showed that RF sensing can extract presence, breathing, movement, gait, sleep, and more, without cameras or wearables.

The bottleneck now is deployment.

The last eighteen months changed the substrate enough that a new kind of company makes sense.
Not another vertically integrated sensing company.
A deployment-layer company.

## The invention era is over

In the last wave, teams had to build almost everything themselves:

- proprietary radar or heavily customized hardware
- custom signal pipelines
- bespoke models per condition
- cloud-heavy inference because the device could not carry the load
- single-device installs that behaved more like research projects than product rollouts

That made sense then.
It does not make sense now.

Three things changed.

## 1. 802.11bf turned sensing into a platform target

On September 26, 2025, IEEE published 802.11bf-2025.
WLAN sensing is no longer a paper category.
It is a standardized extension to the WiFi stack.

That matters for one reason.
Chip vendors now have a real target.

Over the next few years, sensing-aware WiFi silicon will stop being weird.
That means new companies should spend less time pretending to be hardware labs and more time building the system above the radio.

## 2. CSI foundation models went public

For a long time, WiFi sensing had the worst possible ML profile:
small datasets, custom pipelines, fragile generalization, and no shared model substrate.

That changed in 2024 and 2025.

- **WiFo-2** released the LH-CSI dataset, 11.6 billion CSI points across 78 subsets.
- **AM-FM** trained on CSI-Bench, 461 hours across 26 environments, 35 users, and 16 device types.
- **Tiny-WiFo** showed that large CSI models can be distilled into smaller students for edge deployment.
- **WiFo-CF** validated the unified-foundation-model approach across heterogeneous channel configurations.

The implication is simple.
A serious team in 2026 fine-tunes.
It does not pretrain from scratch.

That is the same shift NLP went through.
Once the substrate exists, the winners are not the teams rebuilding the substrate.
They are the teams shipping on top of it.

## 3. Edge inference stopped being a benchmark flex

Keeping raw biometric signals on-device is not just faster.
It is the sane trust posture.

Under GDPR, raw ambient-biometric streams are an unnecessary liability if they leave the room.
Under the EU AI Act, any high-risk deployment has to survive scrutiny around transparency, oversight, monitoring, and technical documentation.

That work gets much uglier when raw signals travel.
It gets much cleaner when predictions travel and raw CSI does not.

So edge inference is not a latency trick anymore.
It is part of the product thesis.

## What the next company should look like

If the substrate changed, the company shape should change too.

The next company in WiFi sensing should look like this:

- commodity hardware, not bespoke radar
- foundation-model fine-tuning, not from-scratch pretraining
- on-device inference, not raw biometric streams sent to the cloud
- multi-room deployment, not one-off single-device installs
- operational simplicity, because real facilities do not care about your beautiful lab demo

That is the gap I care about.

Not proving the physics.
Not publishing one more model paper.
Not selling a research project dressed up as a startup.

Deployment.

## Why the first wedge is aging-in-place

Pharma trial RPM is real.
It is also a brutal first market for a small team.

The sales cycles are long.
The buyers are concentrated.
The regulatory overhead is heavy.
The feedback loops are slow.

That is a terrible place to learn fast.

Assisted living, home care, and senior living are a better first wedge.

The same underlying system can monitor presence, breathing, motion, and eventually falls.
But the go-to-market motion is different:
wellness and safety first,
no medical claims,
faster install cycles,
monthly recurring revenue,
real operating feedback.

You do not build a deployment layer by waiting two years for your first enterprise pilot.

## What I am building

That is what this repo is.

The current stack is intentionally simple:

- **ESP32-S3** for RF capture
- **Jetson Nano** for local ingest, preprocessing, and inference scaffolding
- classical baselines first
- learned deployment models later

The order matters.

First the ingest contract.
Then the pipeline.
Then baseline estimators.
Then real hardware validation.
Then learned models.

Anything else is slideware.

Right now the repo already proves the parts that deserve to be proven first:

- a stable ESP32 -> Jetson data path
- a synthetic end-to-end simulator
- motion and breath baselines
- real CSI capture bring-up
- a privacy-safe visualizer path for demo and calibration support

The visualizer matters for explanation and demo value.
It is not the product.
The product thesis remains WiFi-first.

## What is not proven yet

This part matters because honesty is part of the moat.

I do not know yet how painful cross-environment generalization will be in real facilities.
That is the central technical risk.

I do not know yet which route to market wins first: direct facility sales or distribution through care platforms.

I do not know yet what production 802.11bf silicon will cost when bought at the scale that matters.

Those are real uncertainties.
They do not break the architecture.
They define the work.

## The bet

The bet is not that WiFi sensing works.
That bet has already been won.

The bet is that the next valuable company in this category will be the one that makes deployment boring.

Cheap hardware.
On-device inference.
No cameras.
No wearables.
No raw biometric data leaving the room.
A system that can actually survive a real installation.

That is what I am building in the open.

If you are working on RF sensing, edge AI, privacy-first healthtech, or aging-in-place infrastructure, I want to talk.

[X: @RenatoLagos](https://x.com/RenatoLagos)
