#!/bin/bash
# --- ADD SWAP SPACE ---
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile swap swap defaults 0 0' >> /etc/fstab

# 1. Update and Install Docker & Git
apt-get update
apt-get install -y ca-certificates curl gnupg git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=\"$(dpkg --print-architecture)\" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 2. Clone the Repository
# We clone into /home/ubuntu/app
git clone https://github.com/AG7-ES/nlp-pipeline-repo.git /home/ubuntu/app
cd /home/ubuntu/app

# 3. Create .env file
# Terraform fills in these variables during the Launch Template creation.
# Docker Compose will automatically read this file.
cat <<EOT >> .env
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=${POSTGRES_DB}
DD_API_KEY=${DD_API_KEY}
EOT

# 4. Start the Application
# --build ensures the local Dockerfile in ./fastapi_app is built
docker compose up -d --build
