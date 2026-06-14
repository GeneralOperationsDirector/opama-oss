#!/usr/bin/env bash
# Docker installation helper for Ubuntu

set -e

echo "🐳 Docker Installation Helper for Ubuntu"
echo "========================================"
echo ""

# Check Ubuntu version
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "📋 Detected: $NAME $VERSION"
else
    echo "⚠️  Cannot detect OS version"
fi

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
    echo "🔐 Will use sudo for installation"
fi

echo ""
echo "This script will install:"
echo "  - Docker Engine"
echo "  - Docker Compose V2 (plugin)"
echo "  - Required dependencies"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

echo ""
echo "📦 Step 1: Installing dependencies..."
$SUDO apt-get update
$SUDO apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

echo ""
echo "🔑 Step 2: Adding Docker's official GPG key..."
$SUDO mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo ""
echo "📝 Step 3: Setting up the repository..."
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null

echo ""
echo "📦 Step 4: Installing Docker Engine..."
$SUDO apt-get update
$SUDO apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

echo ""
echo "👥 Step 5: Adding current user to docker group..."
$SUDO usermod -aG docker $USER

echo ""
echo "✅ Docker installation complete!"
echo ""
echo "🔄 IMPORTANT: You need to log out and log back in for group changes to take effect"
echo "   Or run: newgrp docker"
echo ""
echo "✓ Verify installation:"
echo "   docker --version"
echo "   docker compose version"
echo ""
echo "🚀 Next steps:"
echo "   1. Log out and log back in (or run 'newgrp docker')"
echo "   2. Run: ./start-docker.sh"
echo ""
