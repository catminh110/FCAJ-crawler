#!/bin/bash
set -ex

LOG_FILE="/var/log/fcaj-setup.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== [$(date)] Starting FCAJ Crawler EC2 Setup ==="

export DEBIAN_FRONTEND=noninteractive

# Update system
apt-get update -y
apt-get upgrade -y

# Install essential dependencies
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    nginx \
    curl \
    wget \
    ca-certificates \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2t64 || apt-get install -y libasound2

# Clone repository to /opt/fcaj-crawler
if [ -d "/opt/fcaj-crawler" ]; then
    echo "Updating existing repository..."
    cd /opt/fcaj-crawler
    git pull origin main || true
else
    echo "Cloning repository..."
    git clone https://github.com/catminh110/FCAJ-crawler.git /opt/fcaj-crawler
fi

cd /opt/fcaj-crawler

# Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Install Playwright Chromium with system dependencies
playwright install --with-deps chromium

# Fix permissions for ubuntu user
chown -R ubuntu:ubuntu /opt/fcaj-crawler

# Setup systemd service
cp /opt/fcaj-crawler/deploy/fcaj-crawler.service /etc/systemd/system/fcaj-crawler.service
systemctl daemon-reload
systemctl enable fcaj-crawler.service
systemctl restart fcaj-crawler.service

# Setup Nginx
cp /opt/fcaj-crawler/deploy/nginx-fcaj.conf /etc/nginx/sites-available/fcaj
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/fcaj /etc/nginx/sites-enabled/fcaj
nginx -t
systemctl restart nginx

echo "=== [$(date)] FCAJ Crawler Setup Complete Successfully ==="
