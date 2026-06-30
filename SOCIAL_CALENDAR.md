# Social Calendar

## Goal

- Turn repo progress into a 4-week build-in-public rhythm.
- Create credibility with assisted-living operators, technical peers, and investors without overstating product maturity.
- Keep the workload realistic for a solo founder: 2 short posts + 1 deeper asset per week.

## Messaging Guardrails

- Publish only claims already backed by code, docs, tests, or verified demos.
- Keep the product thesis explicit: no cameras, no cloud, no wearables.
- Treat the camera-assisted visualizer as demo/calibration scaffolding, not the shipped product.
- Say "backlog" when it is backlog. Trust compounds when scope is honest.

## Editorial Voice

- Lead with the punchline, not the warm-up.
- Use short sentences, hard contrasts, and strong nouns.
- Sound technical, opinionated, and slightly confrontational, but never vague.
- Attack bad assumptions, not people.
- Prefer "this matters because..." over generic inspiration.
- Cut filler, hedging, and fake-founder optimism.

### Voice Formula

- Hook: one blunt line that creates tension.
- Reframe: explain what most people get wrong.
- Proof: name the concrete technical or market facts.
- Thesis: say the bet in one sharp sentence.
- Close: ask for a specific conversation, intro, or reaction.

### Avoid

- Generic motivation-post energy.
- Corporate innovation language.
- Long throat-clearing intros.
- Soft claims like "excited to share" or "huge opportunity" without evidence.
- Threads that sound like investor deck leftovers.

## Audience Priority

1. Assisted-living and home-care operators who could become design partners.
2. Technical peers who can amplify, critique, or contribute.
3. Investors and grant reviewers who need a sharp category + execution narrative.

## Core Narrative Pillars

| Pillar | What to say | Source of truth |
| --- | --- | --- |
| Category timing | WiFi sensing just commoditized: 802.11bf, public CSI foundation models, and edge-regulatory tailwinds changed the game. | `README.md`, `docs/positioning.md`, `docs/blog/01-wifi-sensing-deployment-layer.md` |
| Product thesis | This repo is the deployment layer for ambient perception in aging-in-place wellness. | `README.md`, `docs/positioning.md` |
| Technical proof | ESP32 -> Jetson ingest, baseline estimators, real CSI capture, and privacy-safe visualizer work are the proof path. | `README.md`, `docs/architecture.md` |
| Founder trust | Publish honest progress, constraints, risks, and asks instead of startup cosplay. | This file + Linear issue history |

## Execution System

- Narrative truth lives in `README.md`, `docs/positioning.md`, `docs/architecture.md`, and `docs/blog/01-wifi-sensing-deployment-layer.md`.
- Planning truth lives in this file.
- Execution truth lives in the Linear project `Content Calendar - Wifi Sensor`.
- Every publishable asset gets one Linear issue with a due date, channel label, and milestone.

### Linear Status Policy

- `Backlog`: good idea, not committed this month.
- `Todo`: committed for this calendar, scoped, due date set.
- `In Progress`: drafting copy or capturing the asset.
- `In Review`: final edit, proofread, or media polish pending.
- `Done`: published, with the final URL pasted back into the issue.

## 4-Week Calendar

| Date | Channel | Asset | Primary goal | Linear |
| --- | --- | --- | --- | --- |
| 2026-05-26 | LinkedIn | Why WiFi sensing just commoditized | Frame the category window and attract technical/investor attention. | `REN-5` |
| 2026-05-28 | X | No cameras, no cloud, no wearables | Make the privacy/product thesis memorable in one short founder post. | `REN-7` |
| 2026-05-29 | Blog | Publish deployment-layer article | Ship the anchor long-form piece that the rest of the month can reference. | `REN-10` |
| 2026-06-02 | LinkedIn | ESP32 to Jetson architecture post | Show the concrete system shape without pretending the backlog is done. | `REN-9` |
| 2026-06-04 | X | Aging-in-place is the beachhead | Explain the market wedge and invite operator/design-partner conversations. | `REN-8` |
| 2026-06-05 | Demo | Synthetic-to-real pipeline proof clip | Show that the pipeline is real, not just narrative. | `REN-6` |
| 2026-06-09 | LinkedIn | Edge inference is a trust posture | Connect privacy, compliance, and on-device inference into one clear argument. | `REN-15` |
| 2026-06-11 | Demo | Privacy-safe visualizer preview | Use the visualizer for marketing while keeping the product message WiFi-first. | `REN-11` |
| 2026-06-12 | X | What is proven vs what is backlog | Increase trust by drawing a hard line between shipped proof and roadmap. | `REN-13` |
| 2026-06-16 | X | Lessons from real CSI capture | Turn field learning into a compact technical credibility post. | `REN-16` |
| 2026-06-18 | LinkedIn | From synthetic baseline to real hardware | Tell the month story: honest baseline, real validation, next step. | `REN-14` |
| 2026-06-19 | Blog | Monthly build log and asks | Close the month with progress, risks, and explicit asks for intros/help. | `REN-12` |

## Weekly Operating Rhythm

- Monday: review the next milestone and move only the current week's issues into `In Progress`.
- During drafting: reuse repo diagrams, screenshots, and benchmark snippets instead of inventing new narrative from scratch.
- After publishing: paste the URL into the Linear issue, move it to `Done`, and note any learnings in the issue comments.
- End of week: kill or rescope any asset that no longer matches current proof.

## Non-Negotiables

- Do not claim fall detection, foundation-model fine-tuning, or multi-room deployment as done.
- Do not let camera demos blur the WiFi-first product thesis.
- Do not create more content than the evidence can carry.
