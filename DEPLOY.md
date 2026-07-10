# ClawStation 24/7 Hosting Runbook

This document describes how to deploy the ClawStation gaming backend and
Telegram bot to a VPS for always-on operation.

## 1. VPS provisioning

Recommended: Hetzner CX22 (2 vCPU, 4 GB RAM, 40 GB NVMe) or equivalent.

- Install Ubuntu 24.04 LTS.
- Open ports 22 (SSH), 80 (HTTP), and 443 (HTTPS).
- Point a DNS A record for your domain (e.g. `clawstation.example`) at the VPS IP.

## 2. Install Docker

```bash
# Add Docker's official GPG key and repository, then install.
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

## 3. Deploy the application

1. Clone the repository and change into the worktree.
2. Copy `.env.example` to `.env` and fill in all required secrets:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `CIRCLE_API_KEY`
   - `CIRCLE_CLIENT_KEY`
   - `CIRCLE_ENTITY_SECRET`
   - `CIRCLE_WALLET_SET_ID`
   - `TELEGRAM_BOT_TOKEN_CLAWSTATION` (falls back to `TELEGRAM_BOT_TOKEN`)
   - Optional: `MINIAPP_URL`, `WEBHOOK_URL`, `CIRCLE_WEBHOOK_SECRET`, `DATABASE_URL`
3. Build and start the services:

```bash
cd /path/to/sideQuest/.worktrees/clawstation-foundation
docker compose -f gaming/docker-compose.yml up -d --build
```

4. Verify the API is healthy:

```bash
curl http://<vps-ip>:8000/api/healthz
```

## 4. Configure Caddy

Install Caddy:

```bash
sudo apt install -y caddy
```

Copy the example Caddyfile, edit the domain, and reload:

```bash
sudo cp gaming/deploy/Caddyfile /etc/caddy/Caddyfile
# Replace clawstation.example with your real domain.
sudo sed -i 's/clawstation.example/your-domain.example/g' /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy will automatically provision and renew a Let's Encrypt certificate.

## 5. Uptime monitoring

Create an UptimeRobot monitor pointing at:

```
https://<your-domain>/healthz
```

The `/healthz` path is answered directly by Caddy without hitting the backend,
so it is fast and cheap. For a deeper check, point a secondary monitor at
`/api/healthz` which validates Supabase connectivity.

## 6. Log rotation

Docker Compose already configures the `json-file` log driver with
`max-size: 10m` and `max-file: 3` per service. View logs with:

```bash
docker compose -f gaming/docker-compose.yml logs -f --tail 100 clawstation-api
docker compose -f gaming/docker-compose.yml logs -f --tail 100 clawstation-bot
```

## 7. Host-level health check

Run `gaming/deploy/healthcheck.sh` from the VPS to verify the local API and
Supabase connectivity:

```bash
bash gaming/deploy/healthcheck.sh
```

## 8. Environment backup note

`.env` contains secrets. Back it up in a password manager or encrypted store;
do not commit it. After rotating any secret, run:

```bash
docker compose -f gaming/docker-compose.yml up -d --force-recreate
```

## 9. CI/CD deployments

Pushing a Git tag matching `v*` triggers `.github/workflows/clawstation-deploy.yml`,
which builds and pushes a Docker image to GHCR and pulls it on the VPS via SSH.
Required repository secrets:

- `GHCR_TOKEN`
- `VPS_HOST`
- `VPS_USER`
- `VPS_SSH_KEY`
