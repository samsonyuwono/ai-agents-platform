# Raspberry Pi Sniper Deployment Plan

## Why Not Just Use the Laptop?

The laptop works perfectly — residential IP, real macOS browser, no bot detection issues. The only problem is you need it **open at drop time**. A dedicated device solves this by being always-on.

| | Laptop | Raspberry Pi | Mac Mini |
|---|---|---|---|
| **Always-on** | No — must be open at drop time | Yes | Yes |
| **Bot detection risk** | None (proven to work) | Medium — ARM Linux fingerprint is untested against PerimeterX | Very low — macOS + real GPU = same fingerprint as laptop |
| **Cost** | $0 (already own) | ~$120 (board + accessories) | ~$160-250 (used M1) |
| **Power** | ~$15/yr | ~$9/yr | ~$35/yr |
| **Browser fingerprint** | macOS + Apple GPU + real display | Linux + VideoCore VII GPU + no display | macOS + Apple GPU + no display |
| **User-Agent match** | Real macOS Chrome | Mismatch (hardcoded macOS UA vs `Linux aarch64` platform) — must fix | Real macOS Chrome |
| **Setup effort** | None | Medium (OS flash, Playwright ARM, systemd) | Low (macOS already runs everything) |

**Bottom line:** The Pi is the cheapest always-on option but has a real risk of PerimeterX flagging it. A used Mac Mini is ~$120 more but nearly guaranteed to work since it's the same OS/browser as your laptop. The Pi is worth trying first — if it fails, buy the Mac Mini.

---

## Hardware

**Raspberry Pi 5, 8GB RAM** (~$80 board, ~$120 total)

- 8GB is important — Chromium peaks at ~583MB, plus OS and Python overhead
- Pi 4 (4GB) would be marginal
- Pi 5 has VideoCore VII GPU with OpenGL ES 3.1 — real hardware GPU rendering (not SwiftShader like the VPS)

**Accessories:**
- Official Pi 5 power supply (27W USB-C, mandatory for stability)
- Active cooler or heatsink case (Chromium generates heat)
- Ethernet cable (preferred over WiFi for drop-time reliability)
- 32GB+ microSD card (Class 10/A2)

**Total: ~$120**

---

## OS Setup

**Raspberry Pi OS 64-bit (Debian 12 Bookworm-based)**

Playwright officially supports Debian 12 on arm64. Use the Raspberry Pi Imager to flash with:

- SSH enabled (with your laptop's public key)
- Hostname: `sniper-pi`
- Locale: `en_US.UTF-8`
- Timezone: `America/New_York`
- WiFi pre-configured (for initial setup before plugging in ethernet)

**Static IP:** Assign via router DHCP reservation (more reliable than OS-level static IP). Note the IP (e.g., `192.168.1.100`).

---

## Playwright ARM64 Compatibility

**Status: Officially supported.**

- Playwright supports Debian 12 and Ubuntu 22.04/24.04 on arm64 for Chromium
- `playwright install chromium` downloads ARM64-native binaries from Playwright's CDN
- Python package includes ARM64 wheels
- Historical ARM issues (pre-2023) are resolved in current versions (1.40+)

**Installation:**
```bash
pip3 install playwright>=1.40.0
python3 -m playwright install chromium
python3 -m playwright install-deps  # system libraries (libgbm, libasound, etc.)
```

---

## The Critical Unknown: Will PerimeterX Accept the Pi?

The VPS failed on 4 layers. Here's how the Pi stacks up:

| Signal | VPS (failed) | Pi (predicted) | Laptop (works) |
|---|---|---|---|
| IP reputation | Datacenter (flagged) | Residential (clean) | Residential (clean) |
| WebGL renderer | `SwiftShader` (software, flagged) | `V3D 7.1.x` (real GPU) | Apple GPU |
| navigator.platform | `Linux x86_64` | `Linux aarch64` | `MacIntel` |
| Canvas fingerprint | Software-rendered | Hardware GPU | Hardware GPU |
| TCP/TLS stack | Linux server | Linux (same risk) | macOS |
| Audio context | Linux ALSA | Linux ALSA | macOS CoreAudio |

**The Pi fixes the two biggest VPS failures** (datacenter IP and fake GPU). The remaining risk is whether PerimeterX cross-references the user-agent (currently hardcoded as macOS Chrome) against `navigator.platform` (which would report `Linux aarch64`). This mismatch is a fixable code issue — update the user-agent to match the actual platform.

**Assessment: Medium-high probability of success.** If it fails, the likely cause is general Linux headless detection, not a Pi-specific issue.

---

## Deployment Steps

### 1. Initial Pi setup (SSH in)
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git
```

### 2. Clone repo and create venv
```bash
git clone https://github.com/samsonyuwono/ai-agents-platform.git ~/ai-agents
cd ~/ai-agents
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m playwright install chromium
python3 -m playwright install-deps
```

### 3. Configure environment
```bash
# SCP .env from laptop
scp .env pi@sniper-pi:~/ai-agents/.env

# Edit on Pi: set browser mode
# RESY_CLIENT_MODE=browser
# RESY_BROWSER_HEADLESS=true
```

### 4. Run a manual test (the critical gate)
```bash
python3 scripts/run_sniper.py le-gratin 2026-03-20 "6:00 PM" --max-attempts 3
```

If slots come back → PerimeterX is passing the Pi. Proceed.
If "No slots available" → try fixing user-agent, then Camoufox, then Mac Mini.

### 5. Set up systemd service

Create `/etc/systemd/system/sniper.service`:
```ini
[Unit]
Description=Reservation Sniper Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/ai-agents
EnvironmentFile=/home/pi/ai-agents/.env
ExecStart=/home/pi/ai-agents/venv/bin/python3 /home/pi/ai-agents/scripts/sniper_worker.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable sniper
sudo systemctl start sniper
```

### 6. Update laptop config
Add to your `.env`:
```
SNIPER_REMOTE_HOST=pi@192.168.1.100
```

Now `export_resy_session.py` and SSH job scheduling target the Pi.

---

## Scheduling Jobs from Laptop

**SSH directly (simplest):**
```bash
ssh pi@sniper-pi "cd ~/ai-agents && python3 scripts/run_sniper.py fish-cheeks 2026-03-15 '7:00 PM' --at '2026-03-08 09:00'"
```

**Shell alias:**
```bash
alias snipe="ssh pi@sniper-pi 'cd ~/ai-agents && python3 scripts/run_sniper.py'"
# Usage:
snipe fish-cheeks 2026-03-15 "7:00 PM" --at "2026-03-08 09:00"
snipe --list
snipe --cancel 5
```

**Sync database (not recommended):** Overwrites the Pi's DB. Use SSH job creation instead.

---

## Code Changes Needed

### Fix user-agent mismatch
`utils/resy_browser_client.py` line 148 hardcodes a macOS user-agent. On the Pi, `navigator.platform` reports `Linux aarch64`, creating a detectable mismatch. Fix: detect platform at runtime and use a matching user-agent.

### Pi-specific systemd service
Create `deploy/sniper-pi.service` with Pi user, venv path, and working directory.

### Deploy script adaptation
Update `scripts/deploy_sniper.sh` to support Pi target (venv install, Pi paths, skip swap if 8GB RAM).

---

## Monitoring

```bash
# Live logs
ssh pi@sniper-pi "journalctl -u sniper -f"

# Today's activity
ssh pi@sniper-pi "journalctl -u sniper --since today"

# Service status
ssh pi@sniper-pi "systemctl status sniper"
```

Auto-restart is handled by systemd (`Restart=on-failure`). The worker auto-resets stale `active` jobs on startup.

---

## SD Card Health

microSD cards degrade with writes. Mitigations:
- Use a quality A2-rated card
- Mount `/tmp` and `/var/log` as tmpfs to reduce writes
- SQLite writes are minimal (small updates per job)
- For long-term reliability, consider USB SSD boot (Pi 5 supports this natively)

---

## Fallback: If Pi Gets Flagged

1. **Fix user-agent** — eliminate platform/UA mismatch (quick code fix)
2. **Try Camoufox** — Firefox-based, C++-level fingerprint spoofing, supports ARM64 Linux, uses Playwright API (minimal code migration)
3. **Buy a used Mac Mini M1** (~$160-250) — guaranteed to work, same fingerprint as laptop, macOS uses `launchd` instead of `systemd` but the sniper code runs unchanged

---

## Cost Comparison

| Option | Hardware | Monthly | Bot Detection | Always-On |
|---|---|---|---|---|
| Laptop (status quo) | $0 | $0 | Works | No |
| Raspberry Pi 5 | ~$120 | ~$1 | Medium risk | Yes |
| Mac Mini M1 (used) | ~$200 | ~$3 | Very low risk | Yes |
| VPS (current) | $0 | $6 | Fails | Yes |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| PerimeterX flags ARM Linux | Medium | Core use case fails | Camoufox, then Mac Mini fallback |
| Playwright ARM install fails | Low | Blocks project | Use system Chromium via `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` |
| Pi overheats during Chromium | Low | Service crashes | Active cooler + `Restart=on-failure` |
| SD card failure | Low-Medium | Data loss | USB SSD boot, SQLite backups |
| Home internet outage at drop | Low | Missed booking | UPS for router + Pi |
| Power outage | Low | Service stops | UPS, auto-start on boot |

---

## Implementation Sequence

1. Order Raspberry Pi 5 8GB + accessories (~$120, 2-3 day shipping)
2. Flash OS, configure SSH, static IP, timezone
3. Deploy repo, install Playwright + Chromium on ARM64
4. **Run manual test** — this is the go/no-go gate
5. Fix user-agent if needed
6. If still flagged: try Camoufox → Mac Mini
7. Enable systemd service
8. Update laptop `SNIPER_REMOTE_HOST` to point to Pi
9. Test end-to-end: schedule from laptop, verify it fires on Pi
