# ClawStation 24/7 Hosting Runbook

This document describes how to deploy the ClawStation gaming backend and
Telegram bot to a VPS for always-on operation. Production runs on Railway
(docs/RAILWAY_DEPLOY.md); restore, pause, reconciliation and incident steps
are in docs/RUNBOOK.md.

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
3. Build and start the services (first run on a new volume only needs
   `BOARDMAN_DATA_INIT=1` so the boot guard accepts the empty volume):

```bash
cd /path/to/boardman
BOARDMAN_DATA_INIT=1 docker compose up -d --build   # first time
docker compose up -d --build                        # afterwards
```

   Compose runs three containers from `Dockerfile.akash`: `boardman-api`
   (builder webhooks + API), `boardman-bot` and `boardman-house` (the house
   session). All read `./.env` and share the named volume `boardman-data`
   mounted at `/data` (state in `/data/agentic`). `docker compose down -v`
   deletes that volume — never run it on a host with real balances.

4. Verify the API is healthy:

```bash
curl http://<vps-ip>:8000/api/healthz
curl http://<vps-ip>:8000/api/health/deep   # 503 = something needs attention
```

## 4. Configure Caddy

Install Caddy:

```bash
sudo apt install -y caddy
```

Copy the example Caddyfile, edit the domain, and reload:

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
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
so it is fast and cheap. Point a second monitor at `/api/health/deep`, which
checks event-loop lag, that the data volume is writable, the house-session
heartbeat and the supervised processes, and answers 503 on failure.

## 6. Log rotation

Docker Compose already configures the `json-file` log driver with
`max-size: 10m` and `max-file: 3` per service. View logs with:

```bash
docker compose logs -f --tail 100 boardman-api
docker compose logs -f --tail 100 boardman-bot
docker compose logs -f --tail 100 boardman-house
```

Builder-webhook output is prefixed `[wh:<name>]`; supervisor lines are
prefixed `[akash]`.

## 7. Host-level health check

Run `deploy/healthcheck.sh` from the VPS to verify the local API and
Supabase connectivity:

```bash
bash deploy/healthcheck.sh
```

## 8. Environment backup note

`.env` contains secrets. Back it up in a password manager or encrypted store;
do not commit it. After rotating any secret, run:

```bash
docker compose -f docker-compose.yml up -d --force-recreate
```

## 9. CI/CD

- `.github/workflows/ci.yml` — every pull request and push to `main`: pytest
  (Python 3.12, same as the images), frontend `tsc` + `next build`, hardhat
  tests, and vitest for both `engines/afm` packages. Uses no secrets.
- `.github/workflows/akash-image.yml` and `docker-publish.yml` — build
  `Dockerfile.akash` on `main` and push to GHCR with the built-in
  `GITHUB_TOKEN`.
- Railway deploys `main` itself (GitHub integration); there is no SSH deploy
  workflow.
