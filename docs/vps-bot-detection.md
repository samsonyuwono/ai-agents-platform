# VPS Bot Detection — Resy Blocking

## Problem

Resy uses PerimeterX/HUMAN bot detection which blocks both API and browser requests from the DigitalOcean VPS (`159.89.41.103`). The page loads but a CAPTCHA challenge prevents availability slots from rendering. This affects both:

- **API mode**: `/4/find` endpoint returns 0 slots from data center IPs
- **Browser mode**: Page loads but calendar never renders time slots (CAPTCHA intercepts)

Evidence from VPS screenshot: page shows restaurant info but no `ReservationButton` elements, and HTML contains CAPTCHA markers.

## Options Evaluated

### 1. Browser Stealth Hardening — TESTED, FAILED

Added `playwright-stealth` (v2.0.2) to patch ~15 browser fingerprinting signals: WebGL renderer, canvas fingerprint, navigator.webdriver, chrome.runtime, fonts, languages, platform, etc.

- **Branch**: `experiment/playwright-stealth`
- **Result**: Stealth evasions applied successfully but had no effect. Page still loads 45 buttons with zero `ReservationButton` elements. PerimeterX detects the VPS via IP reputation and OS-level fingerprinting (TCP/TLS stack, GPU absence, audio context) that browser-level patches cannot address.
- **Test**: Job #38 — Le Gratin on 2026-03-15, 3 polls, all returned "No slots available"

### 2. Pre-Authenticated Session Upload — TESTED, PARTIALLY WORKED

Built `scripts/export_resy_session.py` to export full Playwright `storage_state` (cookies + localStorage with PerimeterX fingerprinting tokens) from laptop, SCP to VPS.

- **Result**: Got past the login check on VPS — a partial win. But PerimeterX still flagged the browser environment during availability checks. Slots did not render despite valid session.
- **Conclusion**: Authentication and bot detection are separate systems. Passing login doesn't bypass the continuous fingerprint evaluation.

### 3. Run Sniper on Home Machine — NOT TESTED

Run the sniper on a Raspberry Pi, Mac Mini, or always-on laptop on a residential network. Real IP + real browser = hardest to detect.

- **Effort**: Medium — set up systemd service on home hardware
- **Cost**: ~$35 (Raspberry Pi) or use existing hardware
- **Risk**: Depends on home network uptime and power reliability
- **Status**: Not tried. This remains the most likely path to fully autonomous browser-mode sniping.

## Current Architecture

After testing all VPS-viable options, the operational model is:

- **VPS** — API-mode bookings only. Works for restaurants where Resy's API returns availability (e.g., Delmonicos). Always-on, 18MB footprint, $6/month. Verified: job #36 booked Delmonicos with laptop closed.
- **Laptop** — Browser-mode bookings. Required for restaurants with aggressive bot detection (e.g., Le Gratin, Temple Court). Residential IP + real browser fingerprint. Laptop must be open at drop time.
- **Session export** — Available as a tool (`export_resy_session.py`) but does not bypass PerimeterX on VPS. May be useful for future platforms with less aggressive detection.

## Why the VPS Can't Be Fixed With Code

PerimeterX evaluates multiple layers that a datacenter VM cannot fake:

1. **IP reputation** — DigitalOcean IP ranges are flagged as datacenter/hosting
2. **TCP/TLS fingerprinting** — Linux server network stack differs from macOS/Windows
3. **Hardware signals** — No real GPU (WebGL renderer is "SwiftShader"), no audio device, no screen
4. **Behavioral analysis** — Headless browser interaction patterns differ from real users

`playwright-stealth` addresses browser JavaScript signals (layer 3 partially), but cannot change layers 1, 2, or the hardware reality of layer 3. A residential proxy would fix layer 1 but not layers 2-4. No combination of software patches can make a Linux VPS indistinguishable from a real user's laptop.
