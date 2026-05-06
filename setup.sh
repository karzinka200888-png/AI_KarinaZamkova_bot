#!/bin/bash
set -e

# Read credentials from environment variables
TG_TOKEN="${TG_TOKEN:?TG_TOKEN is required}"
ANTHROPIC_KEY="${ANTHROPIC_KEY:?ANTHROPIC_KEY is required}"
GH_USER="${GH_USER:?GH_USER is required}"
GH_TOKEN="${GH_TOKEN:?GH_TOKEN is required}"
REPO_NAME="${REPO_NAME:-AI_KarinaZamkova_bot}"
REPO_DIR="/root/$REPO_NAME"

echo ""
echo "=============================="
echo " VPS Setup: $REPO_NAME"
echo "=============================="

echo ""
echo "[1/9] System update..."
apt update && apt upgrade -y

echo ""
echo "[2/9] Install dependencies..."
apt install -y git python3 python3-pip python3-venv

echo ""
echo "[3/9] Configure git..."
git config --global user.email "deploy@server"
git config --global user.name "auto-deploy"

echo ""
echo "[4/9] Clone repository..."
rm -rf "$REPO_DIR"
git clone "https://$GH_USER:$GH_TOKEN@github.com/$GH_USER/$REPO_NAME.git" "$REPO_DIR"
cd "$REPO_DIR"

echo ""
echo "[5/9] Create .env file..."
cat > .env << EOF
TG_TOKEN=$TG_TOKEN
ANTHROPIC_KEY=$ANTHROPIC_KEY
GH_USER=$GH_USER
GH_TOKEN=$GH_TOKEN
REPO_NAME=$REPO_NAME
EOF
chmod 600 .env

echo ""
echo "[6/9] Create Python venv and install packages..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt

echo ""
echo "[7/9] Install systemd services..."
cp mybot.service /etc/systemd/system/
cp cmdrunner.service /etc/systemd/system/
cp autodeploy.service /etc/systemd/system/
cp autodeploy.timer /etc/systemd/system/

echo ""
echo "[8/9] Install autodeploy script..."
cp autodeploy.sh /root/autodeploy.sh
chmod +x /root/autodeploy.sh

echo ""
echo "[9/9] Enable and start services..."
systemctl daemon-reload
systemctl enable --now mybot
systemctl enable --now cmdrunner
systemctl enable --now autodeploy.timer

echo ""
echo "=============================="
echo " Setup complete!"
echo "=============================="
python3 --version
git --version
echo ""
echo "Services status:"
systemctl is-active mybot && echo "  mybot:           RUNNING" || echo "  mybot:           FAILED"
systemctl is-active cmdrunner && echo "  cmdrunner:       RUNNING" || echo "  cmdrunner:       FAILED"
systemctl is-active autodeploy.timer && echo "  autodeploy.timer: RUNNING" || echo "  autodeploy.timer: FAILED"
echo ""
echo "Logs: journalctl -u mybot -f"
