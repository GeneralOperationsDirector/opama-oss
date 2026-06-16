# Ubuntu Setup Guide for opama

## Quick Start on Ubuntu

### Option 1: Using the Installation Script (Recommended)

```bash
# Make the script executable
chmod +x install-docker-ubuntu.sh

# Run the installation script
./install-docker-ubuntu.sh

# Log out and log back in (or run: newgrp docker)

# Start the application
./start-docker.sh
```

### Option 2: Manual Installation

#### 1. Install Docker

```bash
# Update package index
sudo apt-get update

# Install prerequisites
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up the repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt-get update
sudo apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

# Add your user to the docker group
sudo usermod -aG docker $USER

# Log out and log back in for group changes to take effect
# Or run: newgrp docker
```

#### 2. Verify Installation

```bash
# Check Docker version
docker --version
# Should show: Docker version 24.x.x or newer

# Check Docker Compose version
docker compose version
# Should show: Docker Compose version v2.x.x or newer

# Test Docker
docker run hello-world
```

#### 3. Install Node.js (for frontend)

```bash
# Install Node.js 18 LTS
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify
node --version  # Should be v18.x.x or newer
npm --version   # Should be 9.x.x or newer
```

## Running the Application

### Backend (Docker)

```bash
# Start all services
./start-docker.sh

# Check logs
docker compose -f docker-compose.dev.yml logs -f backend

# Stop services
./stop-docker.sh
```

### Frontend (Separate Terminal)

```bash
cd opama-ui
npm install
npm run dev
```

Visit http://localhost:5173

## Ubuntu-Specific Notes

### Docker Compose V2 vs V1

Modern Ubuntu installations use Docker Compose V2 (plugin):
- **V2 Command**: `docker compose` (space, not hyphen)
- **V1 Command**: `docker-compose` (hyphen)

The updated scripts automatically detect which version you have.

### Permissions

If you get permission denied errors:

```bash
# Make sure you're in the docker group
groups

# If docker is not listed:
sudo usermod -aG docker $USER

# Log out and back in, or:
newgrp docker

# Test without sudo
docker ps
```

### Firewall (UFW)

If you use UFW, you may need to allow Docker:

```bash
# Allow Docker to work with UFW
sudo ufw allow from 172.16.0.0/12 to any
```

### Port Conflicts

If ports 8008, 5433, or 6379 are in use:

```bash
# Find what's using port 8008
sudo lsof -i :8008
# Or
sudo netstat -tulpn | grep 8008

# Kill the process or change ports in docker-compose.dev.yml
```

### WSL2 (Windows Subsystem for Linux)

If running Ubuntu on WSL2:

```bash
# Install Docker Desktop for Windows instead
# Then run these commands in WSL2 Ubuntu:
./start-docker.sh

# Docker Desktop handles the Docker daemon
```

## Troubleshooting

### "/usr/bin/env: 'bash\r': No such file or directory"

This is a Windows line ending issue (CRLF vs LF).

**Quick Fix:**
```bash
# Option 1: Use the helper script
./fix-line-endings.sh

# Option 2: Install dos2unix
sudo apt-get install dos2unix
dos2unix *.sh

# Option 3: Manual fix with sed
sed -i 's/\r$//' start-docker.sh stop-docker.sh install-docker-ubuntu.sh
```

**Prevention:**
```bash
# Configure git to use Unix line endings
git config core.autocrlf input

# The .gitattributes file now handles this automatically
```

### "Cannot connect to Docker daemon"

```bash
# Check if Docker is running
sudo systemctl status docker

# If not running, start it
sudo systemctl start docker

# Enable on boot
sudo systemctl enable docker
```

### "Permission denied while trying to connect"

```bash
# Add yourself to docker group
sudo usermod -aG docker $USER

# Apply group changes without logout
newgrp docker
```

### "curl: command not found"

```bash
sudo apt-get update
sudo apt-get install -y curl
```

### Images won't build

```bash
# Clear Docker cache
docker system prune -a

# Rebuild from scratch
docker compose -f docker-compose.dev.yml build --no-cache
```

### Out of disk space

```bash
# Check Docker disk usage
docker system df

# Clean up unused containers, images, and volumes
docker system prune -a --volumes

# WARNING: This removes all stopped containers and unused images!
```

## Development Workflow

### Daily Usage

```bash
# Morning - Start services
./start-docker.sh

# Work on code
# Backend: Files in app/ and services/ auto-reload
# Frontend: cd opama-ui && npm run dev

# Evening - Stop services
./stop-docker.sh
```

### Code Changes

**Backend (Python):**
- Edit files in `app/` or `services/`
- Changes auto-reload in ~2 seconds
- No container rebuild needed

**Frontend (React):**
- Edit files in `opama-ui/src/`
- Instant hot-module replacement
- Runs outside Docker for speed

**Dependencies Changed:**
```bash
# Backend - requirements.txt modified
docker compose -f docker-compose.dev.yml build backend
docker compose -f docker-compose.dev.yml up -d backend

# Frontend - package.json modified
cd opama-ui
npm install
npm run dev
```

### Database

**SQLite (default):**
- File: `./data.db`
- Automatically created on first run
- Persisted across container restarts

**PostgreSQL (optional):**
```bash
# Edit docker-compose.dev.yml, uncomment PostgreSQL lines
# Then restart
docker compose -f docker-compose.dev.yml up -d --build
```

## Performance Optimization

### BuildKit

Enable BuildKit for faster builds:

```bash
# Temporary
DOCKER_BUILDKIT=1 docker compose -f docker-compose.dev.yml build

# Permanent - add to ~/.bashrc
echo 'export DOCKER_BUILDKIT=1' >> ~/.bashrc
source ~/.bashrc
```

### Resource Limits

Ubuntu doesn't limit Docker resources by default, but you can add limits in `docker-compose.dev.yml`:

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
```

## Useful Commands

```bash
# View running containers
docker ps

# View all containers (including stopped)
docker ps -a

# View logs
docker compose -f docker-compose.dev.yml logs -f backend

# Shell into backend container
docker compose -f docker-compose.dev.yml exec backend bash

# Run Python script in container
docker compose -f docker-compose.dev.yml exec backend python scripts/import_cards.py data/

# Check Docker disk usage
docker system df

# View network info
docker network ls
docker network inspect pokemon-dev-network

# View volume info
docker volume ls
```

## Next Steps

1. ✅ Install Docker (use `install-docker-ubuntu.sh`)
2. ✅ Clone the repository
3. ✅ Create `.env.local` with your API keys
4. ✅ Run `./start-docker.sh`
5. ✅ In another terminal: `cd opama-ui && npm run dev`
6. ✅ Open http://localhost:5173

## Getting Help

- **Docker Issues**: https://docs.docker.com/engine/install/ubuntu/
- **Application Issues**: Check `DOCKER_GUIDE.md`
- **Portfolio Feature**: See `PORTFOLIO_IMPLEMENTATION.md`

## System Requirements

- **Ubuntu**: 20.04 LTS or newer
- **RAM**: 4 GB minimum, 8 GB recommended
- **Disk**: 10 GB free space
- **CPU**: 2 cores minimum, 4 cores recommended
