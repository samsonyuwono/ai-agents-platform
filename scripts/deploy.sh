#!/usr/bin/env bash
#
# Deploy the full stack (web API + sniper worker + Caddy) to a remote VPS.
#
# Reads from the local .env file:
#   SNIPER_REMOTE_HOST  — SSH target (e.g. root@1.2.3.4)
#   SNIPER_REMOTE_DIR   — Remote project path (default: /root/ai-agents)
#   DEPLOY_DOMAIN       — Domain for Caddy HTTPS (e.g. api.example.com)
#
# Usage:
#   bash scripts/deploy.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

# --- Load config from .env ---
if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi

SNIPER_REMOTE_HOST=$(grep -E '^SNIPER_REMOTE_HOST=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")
SNIPER_REMOTE_DIR=$(grep -E '^SNIPER_REMOTE_DIR=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")
DEPLOY_DOMAIN=$(grep -E '^DEPLOY_DOMAIN=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")

if [[ -z "$SNIPER_REMOTE_HOST" ]]; then
    echo "Error: SNIPER_REMOTE_HOST not set in .env"
    exit 1
fi

if [[ -z "$DEPLOY_DOMAIN" ]]; then
    echo "Error: DEPLOY_DOMAIN not set in .env"
    exit 1
fi

REMOTE_DIR="${SNIPER_REMOTE_DIR:-/root/ai-agents}"

echo "==> Deploying full stack to $SNIPER_REMOTE_HOST:$REMOTE_DIR"
echo "    Domain: $DEPLOY_DOMAIN"

# --- Step 1: Sync project files ---
echo ""
echo "--- Syncing project files ---"
rsync -avz --delete \
    --exclude '.env' \
    --exclude 'data/' \
    --exclude 'news/' \
    --exclude 'logs/' \
    --exclude '.git/' \
    --exclude '__pycache__/' \
    --exclude '.pytest_cache/' \
    --exclude '*.pyc' \
    --exclude '.claude/' \
    "$PROJECT_DIR/" "$SNIPER_REMOTE_HOST:$REMOTE_DIR/"

# --- Step 2: Ensure swap space (Chromium peaks ~583MB on 1GB VPS) ---
echo ""
echo "--- Ensuring 2GB swap space ---"
ssh "$SNIPER_REMOTE_HOST" "if [ ! -f /swapfile ]; then fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab && echo 'Swap created'; else echo 'Swap already exists'; fi"

# --- Step 3: Install Python dependencies ---
echo ""
echo "--- Installing Python dependencies ---"
ssh "$SNIPER_REMOTE_HOST" "cd $REMOTE_DIR && pip3 install --break-system-packages -r requirements.txt"

# --- Step 4: Install Playwright browsers if needed ---
echo ""
echo "--- Installing Playwright browsers (if needed) ---"
ssh "$SNIPER_REMOTE_HOST" "python3 -m playwright install chromium 2>/dev/null || echo 'Playwright not installed or already up to date'"

# --- Step 5: Install systemd services ---
echo ""
echo "--- Installing systemd services ---"
ssh "$SNIPER_REMOTE_HOST" "cp $REMOTE_DIR/deploy/web-api.service /etc/systemd/system/web-api.service"
ssh "$SNIPER_REMOTE_HOST" "cp $REMOTE_DIR/deploy/sniper.service /etc/systemd/system/sniper.service"
ssh "$SNIPER_REMOTE_HOST" "systemctl daemon-reload && systemctl enable --now web-api sniper"

# --- Step 6: Configure and reload Caddy ---
echo ""
echo "--- Configuring Caddy for $DEPLOY_DOMAIN ---"
ssh "$SNIPER_REMOTE_HOST" "cat > /etc/caddy/Caddyfile <<EOF
$DEPLOY_DOMAIN {
    reverse_proxy localhost:8000
}
EOF
"
ssh "$SNIPER_REMOTE_HOST" "systemctl reload caddy || systemctl restart caddy"

# --- Step 7: Show status ---
echo ""
echo "--- Service status ---"
ssh "$SNIPER_REMOTE_HOST" "systemctl status web-api --no-pager -l" || true
echo ""
ssh "$SNIPER_REMOTE_HOST" "systemctl status sniper --no-pager -l" || true
echo ""
ssh "$SNIPER_REMOTE_HOST" "systemctl status caddy --no-pager -l" || true

echo ""
echo "==> Deployment complete!"
echo ""
echo "Verify:"
echo "  curl https://$DEPLOY_DOMAIN/health"
echo ""
echo "Useful commands:"
echo "  ssh $SNIPER_REMOTE_HOST systemctl status web-api sniper caddy"
echo "  ssh $SNIPER_REMOTE_HOST journalctl -u web-api -f"
echo "  ssh $SNIPER_REMOTE_HOST journalctl -u sniper -f"
echo "  ssh $SNIPER_REMOTE_HOST systemctl restart web-api"
echo "  ssh $SNIPER_REMOTE_HOST systemctl restart sniper"
