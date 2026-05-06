#!/bin/bash
REPO_DIR="/root/AI_KarinaZamkova_bot"
LOG="/var/log/autodeploy.log"

cd "$REPO_DIR" || exit 1

git fetch origin main 2>/dev/null

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    git pull origin main
    source venv/bin/activate
    pip install -r requirements.txt -q
    systemctl restart mybot
    systemctl restart cmdrunner
    echo "$(date): Updated to $(git rev-parse --short HEAD) and restarted" >> "$LOG"
fi
