# Rematch bot free 24/7 — Oracle Cloud Always Free

**This is the real free always-on option.** Not Fly. Not a trial that expires after days.

| | |
|--|--|
| **Cost** | $0 forever if you stay on Always Free shapes |
| **Catch** | Credit card for ID check (Oracle does **not** charge free-tier VMs if you stay free) |
| **Signup** | Sometimes rejects / no capacity — try another home region or retry later |
| **What you get** | Ubuntu VM that runs your Telegram bot 24/7 |

Bot only needs **one process**: `python -m gaming.src.bot.main` (polling). No paid host required.

---

## Step 1 — Create Oracle free account

1. Open: https://www.oracle.com/cloud/free/
2. Click **Start for free**
3. Use a real email + phone
4. Pick a **home region** carefully (you can’t change it later). Try:
   - US East (Ashburn)
   - US Midwest (Chicago)
   - or a region near you that still has free capacity
5. Add a card for verification only

If signup fails (“out of capacity” / declined), wait a day, try another email/region, or use a different network. This is the hardest part of Oracle — the VM itself is easy.

---

## Step 2 — Create a free Ubuntu VM

In Oracle Cloud Console:

1. **Compute → Instances → Create instance**
2. **Name:** `rematch-bot`
3. **Image:** Canonical Ubuntu 22.04 (or 24.04)
4. **Shape:** Always Free
   - Prefer **VM.Standard.A1.Flex** (Ampere ARM)  
     - OCPUs: **1** (or 2 if available)  
     - Memory: **6 GB** (or 12 GB if free budget allows)
   - If Ampere is out of capacity → try **VM.Standard.E2.1.Micro** (AMD free micro; smaller but enough for the bot)
5. **Networking:** create new VCN / subnet defaults are fine
6. **SSH keys:**
   - On your Mac, if you don’t have a key yet:

```bash
ssh-keygen -t ed25519 -C "rematch-oracle" -f ~/.ssh/oracle_rematch -N ""
cat ~/.ssh/oracle_rematch.pub
```

   - Paste the **.pub** contents into Oracle’s SSH key field
7. Create instance → wait until **Running**
8. Copy the **Public IP**

### Open SSH (if needed)

**Networking → Virtual Cloud Networks → your VCN → Security Lists → Default**  
Ingress rule: TCP port **22** from your IP (or `0.0.0.0/0` if you accept the risk).

You do **not** need to open port 8000 for Telegram polling.

---

## Step 3 — SSH in from your Mac

```bash
ssh -i ~/.ssh/oracle_rematch ubuntu@YOUR_PUBLIC_IP
```

(If image user isn’t `ubuntu`, try `opc`.)

---

## Step 4 — Install Python tools on the VM

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip
```

---

## Step 5 — Clone the bot code

Use the branch that has Rematch (example: `clawstation` or your worktree branch pushed to GitHub):

```bash
cd ~
git clone https://github.com/playingsidequest-dotplay/sideQuest.git
cd sideQuest
git checkout clawstation
# or: git checkout social-mvp   # whichever has the bot you want
```

If the repo is private:

```bash
# create a GitHub personal access token (repo read), then:
git clone https://YOUR_GITHUB_USER:TOKEN@github.com/playingsidequest-dotplay/sideQuest.git
```

---

## Step 6 — Copy your `.env` from the Mac

**On your Mac** (new terminal, leave SSH open):

```bash
scp -i ~/.ssh/oracle_rematch \
  /Users/mac/sideQuest/sideQuest/.worktrees/clawstation-foundation/.env \
  ubuntu@YOUR_PUBLIC_IP:~/sideQuest/.env
```

**On the VM**, lock permissions:

```bash
chmod 600 ~/sideQuest/.env
```

---

## Step 7 — Install Python deps

Still on the VM:

```bash
cd ~/sideQuest
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
# if gaming has extra deps file and install fails on missing packages:
# pip install -r gaming/src/backend/requirements.txt
```

Quick smoke test (should start polling, no crash):

```bash
set -a && source .env && set +a
export CLAWSTATION_BOT_MODE=polling
export CLAW_DEFAULT_CHAIN=arc
python -m gaming.src.bot.main
```

In Telegram send `/start`. If it replies → Ctrl+C and continue.

**Important:** stop any bot on your **Mac** first, or Telegram will conflict:

```bash
# on Mac
ps aux | grep 'gaming.src.bot.main' | grep -v grep
kill <PID>
```

---

## Step 8 — Run forever with systemd (survives reboot)

On the VM:

```bash
sudo tee /etc/systemd/system/rematch-bot.service >/dev/null <<'EOF'
[Unit]
Description=Rematch Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/sideQuest
EnvironmentFile=/home/ubuntu/sideQuest/.env
Environment=CLAWSTATION_BOT_MODE=polling
Environment=CLAW_DEFAULT_CHAIN=arc
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/ubuntu/sideQuest/.venv/bin/python -m gaming.src.bot.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable rematch-bot
sudo systemctl start rematch-bot
sudo systemctl status rematch-bot
```

Logs:

```bash
sudo journalctl -u rematch-bot -f
```

---

## Step 9 — Confirm

| Check | How |
|-------|-----|
| Service running | `sudo systemctl status rematch-bot` → **active (running)** |
| Logs polling | `journalctl -u rematch-bot -n 50` |
| Telegram | `/start` replies **Rematch · sideQuest** |
| After reboot | `sudo reboot`, wait 2 min, `/start` again |

---

## Day-to-day commands (on the VM)

```bash
# logs
sudo journalctl -u rematch-bot -f

# restart
sudo systemctl restart rematch-bot

# stop
sudo systemctl stop rematch-bot

# update code
cd ~/sideQuest && git pull && source .venv/bin/activate
pip install -r backend/requirements.txt
sudo systemctl restart rematch-bot
```

Update `.env` on Mac → re-scp → restart service.

---

## Common problems

| Problem | Fix |
|---------|-----|
| Out of capacity creating VM | Other Always Free shape, other AD, or retry later |
| `Permission denied (publickey)` | Wrong key path / wrong user (`ubuntu` vs `opc`) |
| `Conflict: terminated by other getUpdates` | Kill local Mac bot; only one poller |
| Bot silent | `journalctl -u rematch-bot -n 100` — missing env / import error |
| Git private clone fails | Use PAT or deploy key |
| ARM pip wheel fails | Use Ampere carefully; or use E2.1.Micro AMD free shape instead |

---

## What this costs

- **VM:** $0 on Always Free
- **Bandwidth:** free tier includes enough for a Telegram bot
- **Card:** may show $0 auth holds; stay on free shapes → no bill for the VM
- **Do not** create paid shapes / load balancers unless you want charges

Oracle console: check **Billing & Cost Management** occasionally.

---

## If Oracle signup fails for weeks

Honest backups (all imperfect):

1. **Mac + `./gaming/deploy/start_free_local.sh`** — free, only while Mac is awake  
2. **Google Cloud free e2-micro** — free forever in some regions; similar SSH/systemd steps  
3. **Cheapest paid VPS later** (~$4–6/mo Hetzner/DO) — same systemd, zero code change  

There is **no** major host that is both truly free **and** always-on with zero signup friction. Oracle is the best free 24/7 fit for this bot.

---

*Related: `FREE_24_7.md`, local script `gaming/deploy/start_free_local.sh`*
