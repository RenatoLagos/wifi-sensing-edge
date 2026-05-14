# Hardware

The full prototype runs on ~$130 of off-the-shelf hardware.

## Bill of materials

| Item | Qty | Approx USD | Notes |
|------|-----|------------|-------|
| ESP32-S3-DevKitC-1 (8MB PSRAM, 16MB Flash, **N16R8** variant) | 2 | $20 | One acts as monitor, one as packet emitter |
| u.FL pigtail -> SMA female bulkhead, 2.4 GHz, ~10cm | 2 | $4 | DevKitC has u.FL connector on board |
| SMA-male 2.4 GHz antenna, 3-5 dBi, omni | 2 | $6 | Look for "ESP32 external WiFi antenna" |
| SanDisk Ultra MicroSD 32GB Class 10 | 1 | $8 | Logging + Jetson SD card backup |
| USB-C cable, data-rated, 1m | 2 | $6 | Avoid power-only cables (silent flash failures) |
| Jetson Nano 4GB Developer Kit | 1 | already owned | Confirm JetPack 4.6.x before any work |

**Total new spend: ~$50-60 USD**

## Where to buy

- **Amazon (US/EU)**: faster shipping (~7 days), search "ESP32-S3-DevKitC-1 N16R8". Pay the markup if you value time.
- **AliExpress**: official Espressif store sells the same DevKitC for ~$13. Shipping 2-4 weeks. Order TODAY if going this route.
- **Mouser / Digi-Key**: most reliable for the exact `ESP32-S3-DevKitC-1-N16R8` SKU. Pricier but no counterfeits.

Order from **two sources** in parallel — if Amazon delivers first, AliExpress is your backup stock for when something fries.

## What to AVOID

- ESP32-S3 modules without the u.FL connector — you cannot attach an external antenna, and the PCB antenna SNR will not cut it for CSI work.
- The cheaper ESP32 (not S3) — the original ESP32 has less RAM and worse CSI APIs in `esp-csi`.
- USB-A "fast charging" cables — many are power-only. Buy from a brand you trust.

## Pre-flight checklist (before ordering)

- [ ] Confirm you have a USB-C port on your dev machine that can do data (not just power)
- [ ] Confirm your Jetson Nano boots and you can SSH or display to it
- [ ] Confirm JetPack version (`cat /etc/nv_tegra_release` — target 4.6.x)
- [ ] Have a free 2.4 GHz WiFi router OR set up an isolated AP for clean test conditions

## After hardware arrives

1. Flash the **first** ESP32 with the `esp-csi` console example
2. Confirm CSI packets land on UART (no antenna needed for this sanity check)
3. Attach u.FL → SMA antenna, observe SNR improvement
4. Wire the second ESP32 as packet emitter on a fixed channel
5. Pipe the receiver's UART into the Jetson and confirm parse on `jetson/ingest/`

The "first commit with real CSI" milestone in the plan happens **after step 5**.
