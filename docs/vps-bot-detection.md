# VPS Bot Detection — Resy Blocking

## Problem

Resy uses PerimeterX/HUMAN bot detection which blocks both API and browser requests from the DigitalOcean VPS (`159.89.41.103`). The page loads but a CAPTCHA challenge prevents availability slots from rendering. This affects both:

- **API mode**: `/4/find` endpoint returns 0 slots from data center IPs
- **Browser mode**: Page loads but calendar never renders time slots (CAPTCHA intercepts)

Evidence from VPS screenshot: page shows restaurant info but no `ReservationButton` elements, and HTML contains CAPTCHA markers.

## Options to Bypass

### 1. Browser Stealth Hardening (try first)

Add `playwright-stealth` to patch browser fingerprinting signals that PerimeterX detects (WebGL, navigator, WebDriver flags, canvas, fonts, etc.).

- **Effort**: Small — code change + `pip install playwright-stealth`
- **Cost**: Free
- **Risk**: May not be enough; PerimeterX can still flag data center IP ranges

### 2. Pre-Authenticated Session Upload

Log into Resy from a residential IP (laptop), export full cookies + local storage, upload to VPS. If the CAPTCHA only triggers on unauthenticated/new sessions, a warm session from a trusted IP might bypass it.

- **Effort**: Medium — build a session export/import script
- **Cost**: Free
- **Risk**: Session may expire or get invalidated when IP changes

### 3. Run Sniper on Home Machine

Run the sniper on a Raspberry Pi, Mac Mini, or always-on laptop on a residential network. Real IP + real browser = hardest to detect.

- **Effort**: Medium — set up systemd service on home hardware
- **Cost**: ~$35 (Raspberry Pi) or use existing hardware
- **Risk**: Depends on home network uptime and power reliability

## Current Status

- VPS `.env` is set to `RESY_CLIENT_MODE=browser`
- Chromium runs headless with `--no-sandbox` and `--disable-blink-features=AutomationControlled`
- Worker daemon is active but all polls return 0 slots due to CAPTCHA
- Local laptop browser works fine (residential IP, non-headless Chromium)
