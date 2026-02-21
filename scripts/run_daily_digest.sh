#!/bin/bash
# Daily News Digest Cron Job Script

# Set up paths
SCRIPT_DIR="/Users/syuwono/Desktop/Development/ai-agents"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# Load environment variables
cd "$SCRIPT_DIR"
source .env

# Set Python path (update if needed)
PYTHON="/usr/bin/python3"

# Define your topics here (customize as needed)
TOPICS=("AI" "Technology" "SpaceX" "Climate Change")

# Run the digest
echo "================================" >> "$LOG_DIR/cron.log"
echo "Running at: $(date)" >> "$LOG_DIR/cron.log"

$PYTHON "$SCRIPT_DIR/scripts/run_news_digest.py" "${TOPICS[@]}" >> "$LOG_DIR/daily_digest.log" 2>&1

echo "Completed at: $(date)" >> "$LOG_DIR/cron.log"
echo "================================" >> "$LOG_DIR/cron.log"
