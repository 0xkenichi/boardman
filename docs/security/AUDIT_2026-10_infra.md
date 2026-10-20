# Boardman infrastructure audit — October 2026

| | |
|---|---|
| **Scope** | Production backend VM (Oracle Cloud A1, `150.230.112.144`, Ubuntu 24.04.5), Docker stack, Cloudflare tunnel, backups, public GitHub repo and its history, GitHub Actions, Supabase migrations, Vercel/Supabase usage visible from the repo |
| **Method** | Read-only inspection over SSH (sshd -T, ss, iptables, systemctl, docker inspect, stat, dpkg, journalctl), pattern scans that print counts and fingerprints only, static review of the repo at `70a7c64` (origin/main) |
| **Date** | 2026-10-19/20 (VM clock 2026-10-19 23:10 UTC) |
| **Branch** | `audit/infra` |
| **Not in scope** | Application authz, contracts, web front end (separate audits: `audit/money`, `audit/contracts`, `audit/web`); the Cloudflare, Vercel, Supabase and OCI dashboards (no access) |

No secret value was printed, copied or stored during the audit. Where it mattered whether a leaked value is still live, the VM compared SHA-256 hashes and printed only the matching variable names.

## Summary

The perimeter is in decent shape: only SSH is reachable from the internet, the API listens on 127.0.0.1 behind a single-hostname Cloudflare tunnel, password SSH is off, fail2ban and security updates are running, containers are non-root and unprivileged, and no secrets showed up in container logs.

The serious problems are about **keys and recovery**, not the perimeter:

1. The contract **owner** key, the resolver key, the admin key, the keystore secret, the Circle entity secret and the Supabase service-role key all sit in one plaintext `.env` on the box, and every one of them goes into all three containers.
2. The **Circle API key production uses today is public** in git history.
3. **27 plaintext agent private keys** are on the data volume, in every nightly backup, and in a stale 454 MB copy in `~/migrate`. The encrypted keystore that is supposed to replace them has **zero entries** in production.
4. **Supabase migrations grant the public anon role** read/write on approval and audit tables and leave a balance-changing RPC callable by anyone. Whether these grants are live could not be checked from here, so this is the first thing to verify.
5. **Backups are unencrypted, stay on the same VM and have never been restore-tested.** The `.env`, which is needed to use them, is not backed up anywhere. Losing the VM loses the money keys.

### Severity table

Severity is rated for the point where real money goes live. "Testnet today" marks a finding that is a launch blocker but not currently exploitable for real funds.

| ID | Severity | Finding | Status |
|---|---|---|---|
| INF-01 | **Critical** | Contract-owner, resolver and admin keys are hot on the VM in one `.env` that is injected into all 3 containers | Founder action |
| INF-02 | **Critical** | Production Circle API key (and client key) public in git history since 2026-05-18; Telegram bot token in the same commit | Founder action (rotate); guard test added |
| INF-03 | **Critical** (testnet today) | 27 plaintext agent private keys on the volume, in every backup, and in `~/migrate`; keystore rotation never run | Founder action; script encrypts backups |
| INF-04 | **Critical** (unverified) | Supabase: anon/PUBLIC grants on `gaming.tx_approvals` (INSERT/UPDATE), audit tables, `adjust_balance` RPC; tables without RLS | Fixed in branch (migration + verify SQL + test); founder applies |
| INF-05 | **High** | Backups unencrypted, on-box only, world-readable files, never restore-tested, no failure alert; `.env` not backed up | Script ready (`--apply`) + founder steps |
| INF-06 | **High** | Single VM, no rebuild runbook; Always Free idle-reclamation risk | Founder action |
| INF-07 | **High** | No uptime, backup or resource alerting; logs only on the box | Script hook + founder action |
| INF-08 | Medium | Kernel update pending reboot since 2026-10-16; no auto-reboot; cloudflared outdated and not auto-updated | Script ready |
| INF-09 | Medium | Deploy drift: VM runs `fb90227`, 17 commits behind main; security-relevant port binding lives only in an untracked override | Fixed in branch (compose) + founder deploy |
| INF-10 | Medium | SSH: root `without-password`, forwarding on, MaxAuthTries 6, second user `opc` with the same key, ~465 failed auths/day | Script ready |
| INF-11 | Medium | Python dependencies unpinned (`>=`), floating base image tag, unpinned pip | Fixed in branch |
| INF-12 | Medium | Compilers (`build-essential`, `gcc`) shipped in the 1.56 GB runtime image | Fixed in branch |
| INF-13 | Medium | Base compose publishes `0.0.0.0:8000`; no cap_drop / no-new-privileges; Docker-published ports bypass the host firewall | Fixed in branch + script |
| INF-14 | Medium | GitHub Actions pinned by tag, duplicate push-on-main image builds with `packages:write`, no secret or dependency scanning, no Dependabot | Fixed in branch |
| INF-15 | Medium | Every container gets all 122 env vars, including unused `CIRCLE_API_KEY_LIVE` and `NEW_WALLET_PRIVATE_KEY` | Founder action (design below) |
| INF-16 | Low | IPv6 INPUT policy ACCEPT (no global IPv6 today); rpcbind on `0.0.0.0:111` | Script ready |
| INF-17 | Low | cloudflared runs as root; unit changed on disk but not reloaded; no Cloudflare Access/WAF rules seen | Script (opt-in) + founder |
| INF-18 | Low | No `/etc/docker/daemon.json` (no live-restore, no default log cap for ad-hoc containers) | Script ready |
| INF-19 | Low | Container UID 999 equals host user `ocarun` (OCI Run Command); `ubuntu` is root-equivalent (docker group + NOPASSWD sudo) | Accepted / noted |
| INF-20 | Low | Vercel holds the service-role key; `supabaseAdmin.ts` silently falls back to the anon key | Recommendation |

Passed checks are listed at the end.

---

## Findings

### INF-01 — Contract-owner, resolver and admin keys are hot on the VM — Critical

**Evidence**
- `~/boardman/.env` (mode 600, 122 variables) holds `OWNER_PRIVATE_KEY` (66 chars), `ADMIN_PRIVATE_KEY` (66), `BOARDMAN_RESOLVER_KEY` (64), `NEW_WALLET_PRIVATE_KEY` (64), `BOARDMAN_KEYSTORE_SECRET` (64), `CIRCLE_ENTITY_SECRET` (64), `CIRCLE_API_KEY_LIVE`, `SUPABASE_SERVICE_ROLE_KEY`, `PAYSTACK_SECRET_KEY` and `PAYCREST_API_SECRET`. Only lengths were read.
- `docker-compose.yml` loads `env_file: ./.env` into `boardman-api`, `boardman-bot` and `boardman-house`. The variable names in `boardman-api` confirm it. They can be read with `docker inspect` by anyone in the `docker` group, and through `/proc/<pid>/environ` by any code execution in any of the three containers (the Telegram bot is the most exposed of them).
- `src/stack/agentic/onchain.py:960-977` falls back to `ADMIN_PRIVATE_KEY` and then `OWNER_PRIVATE_KEY` as the resolver signer.
- `BoardmanEscrow.setResolver`, `SpectatorPool.setResolver` and `SpectatorPool.sweep` are `onlyOwner`. Whoever holds the owner key can name a new resolver and settle every escrow to themselves.
- The keystore secret sits in the same file as everything it protects, and at present the keystore is empty (INF-03).

**Fix**
1. Move the **owner** role to a multisig (e.g. a 2-of-3 Safe on Arc), call `transferOwnership`, and delete `OWNER_PRIVATE_KEY` from the VM. Owner actions (pause, setResolver, sweep) become a deliberate, human-signed act.
2. Remove the owner/admin fallback from the resolver lookup, so the resolver can only ever be `BOARDMAN_RESOLVER_KEY`. That is a code change for the money/contracts workstream.
3. Remove `NEW_WALLET_PRIVATE_KEY` and `CIRCLE_API_KEY_LIVE` from the VM. No code under `src/` reads them.
4. Give each container only the variables it needs (INF-15).
5. Before mainnet, move the resolver key and the keystore secret into a KMS/HSM. `keystore.py` already reserves a `kms` backend. OCI Vault is available, and its software-protected keys are free.

**Status:** founder action. None of this can be scripted safely without the founder's keys and decisions.

### INF-02 — Production Circle API key public in git history — Critical

**Evidence**
- Commit `4601a32` (2026-05-18, "Session Summary — Everything Built") added `docs/api/CIRCLE_ESCROW_SETUP.md` with a `TEST_API_KEY:` Circle API key and a `TEST_CLIENT_KEY:` client key. The same commit added `src/backend/telegram_webhook.py` with a hard-coded Telegram bot token as the `os.getenv` default.
- Both files were later deleted (`c0f0daa` 2026-05-26, `1a4e318` 2026-08-12). They are still in the history of the **public** repo `0xkenichi/boardman`.
- A hash comparison on the VM shows the leaked values **are the current `CIRCLE_API_KEY` and `CIRCLE_CLIENT_KEY` in production**. The leaked Telegram token does not match any current value. Make sure it is revoked anyway.
- With Circle's API, the API key alone can read every wallet, balance and transaction and can manage webhook subscriptions. Moving funds also needs the entity secret, which was not leaked. It is still a testnet (`TEST_`) key, but production uses it.
- No other high-confidence secret shapes were found in the public history (456 commits; Telegram, Circle, PEM, Paystack, OpenAI/Anthropic, GitHub, AWS, Supabase, JWT service-role, Cloudflare tunnel, Lichess, Stellar seed, EVM key assignments). The other matches were fixtures, placeholders or public on-chain IDs.

**Fix**
1. In the Circle console, create a new API key, put it in the VM `.env`, restart, then **revoke the old key**. The client key goes through the same rotation.
2. In BotFather, check that the bot behind the old token has had its token revoked (`/revoke`).
3. Rewriting history (`git filter-repo`) is optional and only worth doing after rotation, because forks and clones keep the old commits.
4. New guard in this branch: `tests/test_no_secrets_in_tree.py` fails CI if a tracked file contains a credential-shaped string. It reports file:line and the pattern name, never the value.

**Status:** guard added; rotation is a founder action.

### INF-03 — Plaintext agent keys everywhere; keystore never populated — Critical (testnet today)

**Evidence**
- `/data/agentic` has 28 `secrets_*.json` files (mode 0644). **27 contain a plaintext 64-hex private key.** The other one is the sealed house file.
- The encrypted keystore directory (`/data/agentic/keystore`) has **0 entries**. `scripts/rotate_agent_wallets.py` says the legacy keys were derived from a public seed ("treat every legacy address as compromised"). Rotation has not been run in production.
- The nightly backup (`~/snap.py`) tars the whole of `/data/agentic`, so every archive in `~/backups` (5 files, mode 0644 root) carries the 27 keys in the clear.
- `~/migrate/agentic` (454 MB, mode 0775/0644) is a stale copy of the pre-migration data: the same 28 secrets files, a 282 MB SQLite DB, ledger JSON and repair backups. Nothing rotates or deletes it.

**Fix**
1. Settle or cancel open escrows, then run `scripts/rotate_agent_wallets.py` (a dry run first, then `--execute`) inside the API container. It moves balances to fresh keystore keys and seals the plaintext files.
2. After rotation, encrypt the old backups (`harden_vm.sh --encrypt-old-backups`) and archive `~/migrate` encrypted off-box, or delete it once it is confirmed redundant. On cloud block storage, `shred` gives no extra assurance; encrypting is what protects the data.
3. Exclude `secrets_*.json` from `snap.py` once every file is sealed.

**Status:** founder action. Backup encryption is in the script.

### INF-04 — Supabase: anon grants and missing RLS — Critical (unverified)

**Evidence** (repo; the live database could not be inspected)
- `supabase/migrations/000_initial_schema.sql` runs `GRANT SELECT ON gaming.wallet_credit_audit / wallet_debit_audit TO anon, authenticated, public` with no RLS. It also creates `public.adjust_balance(uuid, numeric)` and `adjust_play_points`, which are `EXECUTE`-able by PUBLIC (the Postgres default) and so reachable as `/rest/v1/rpc/adjust_balance` with the public anon key.
- `001_approval_flow.sql` runs `GRANT SELECT, INSERT, UPDATE ON gaming.tx_approvals TO anon, authenticated, public` with no RLS. If the `gaming` schema is exposed in the Data API, anyone can read and **approve** pending spends.
- `public.withdrawals`, `public.football_players`, `gaming.tournaments`, `gaming.tournament_entries` and `gaming.tournament_matches` have no RLS.
- `public.profiles` (balances) was created in the dashboard, so its RLS state is not in the repo. Supabase grants anon full DML on `public` tables by default, so if RLS is off on `profiles`, anyone can `PATCH` a balance.
- Good: every table in the 2026-10 migrations (ledger, channels, Paycrest, self-custody) has RLS enabled and no policies. The backend and the Vercel routes use the service-role key, which bypasses RLS.

**Fix (this branch)**
- `supabase/verify_rls.sql`: read-only queries that list RLS-off tables, anon/authenticated grants, permissive policies, anon-executable functions and anon `USAGE` on `gaming`. **Run it now** and keep the output.
- `supabase/migrations/20261020120000_lock_down_legacy_grants.sql`: idempotent and guarded by `to_regclass`. It enables RLS and revokes anon/authenticated/PUBLIC on every server-only table, enables RLS on `profiles` and revokes anon writes, makes `adjust_*` executable by service_role only, and revokes anon `USAGE` on `gaming`.
- `tests/test_supabase_rls.py`: every created table has RLS, every grant to a public role is revoked, every public function is revoked from PUBLIC, and new migrations must enable RLS in the same file.

**Caveat:** if any page reads `profiles` with the **anon** key (the Vercel helpers only fall back to anon when the service key is missing), enabling RLS hides those rows until a `SELECT` policy is added. Check the output of `verify_rls.sql` query 3 first.

**Status:** fixed in branch; the founder applies the migration.

### INF-05 — Backups: unencrypted, on-box, untested — High

**Evidence**
- Cron `17 3 * * *` runs `~/backup_boardman.sh`, which runs `snap.py` in a `boardman:latest` container as root. It writes `~/backups/boardman-<ts>.tgz` (root, 0644; the directory is 0775) and keeps 14 days. The last run (`20261019T0317Z`) was fine.
- No encryption. Nothing leaves the box (no rclone/rsync/object storage). The archive includes the plaintext keys (INF-03). `backup.log` only prints `ok`. Nothing alerts when a run does not happen.
- No restore has ever been tested, and no script or runbook exists for one.
- The `.env` (keystore secret, resolver key, Circle entity secret) is **not** in the backup. That is correct, but it is not stored anywhere else either. If the VM is lost, the DB comes back and the keys do not.
- The Circle entity-secret **recovery file** is not on the VM (searched). `setup_circle_final.py` tells the operator to "save it safely"; its location is undocumented.

**Fix**
- `scripts/harden_vm.sh --apply --age-recipient age1… [--backup-remote <rclone remote:path>] [--healthcheck-url …]` replaces the backup script. The new script snapshots the data, runs `PRAGMA integrity_check`, encrypts with **age** to an offline public key (the private key never touches the VM), writes a sha256, copies off-box with `rclone --immutable`, pings a dead-man URL on success and on failure, and locks `~/backups` to 0700/0600. `--encrypt-old-backups` converts the 5 existing archives.
- Off-box target: an OCI Object Storage bucket in a **different region** (Always Free includes 20 GB), or Cloudflare R2 / Backblaze B2, with a retention lock.
- Put the `.env` and the Circle recovery file in the founder's password manager (1Password/Bitwarden). Re-save them on every change.
- **Monthly restore drill** (on the founder's machine, not the VM):
  ```sh
  rclone copy <remote>:boardman-backups/boardman-<ts>.tgz.age .
  age -d -i ~/boardman-backup.agekey boardman-<ts>.tgz.age | tar -xz -C restore/
  sqlite3 restore/boardman.sqlite3 'PRAGMA integrity_check; SELECT count(*) FROM ledger_balances;'
  ```
  Write down the date and the row counts in `docs/RUNBOOK.md`.

**Status:** script ready, dry-run tested on the VM; founder steps listed.

### INF-06 — Single point of failure; no VM rebuild runbook — High

**Evidence**
- API, bot, house session, ledger (SQLite), keystore and backups all run on one A1 VM in one availability domain. `docs/RUNBOOK.md` documents Railway, not this VM.
- The VM sits mostly idle: load 0.19 on 4 OCPUs and about 3 of 24 GB RAM in use. Oracle's Always Free terms allow it to **reclaim idle Always Free instances**. Upgrading the tenancy to Pay-As-You-Go keeps the free allowances and removes that risk.
- The Cloudflare tunnel token is only on the VM. Vercel and Supabase are external and survive VM loss.

**Fix**
1. Upgrade the OCI tenancy to PAYG and set a $1 budget alert.
2. Turn on an OCI boot-volume backup policy (Bronze) for a whole-VM restore point. That copy contains the `.env`, so keep the policy in the same compartment and restrict who can read it.
3. Write `docs/RUNBOOK.md §VM rebuild`: new A1 instance, `harden_vm.sh --apply`, Docker, clone, `.env` from the password manager, `docker volume create boardman-data`, restore the latest backup into it, `BOARDMAN_DATA_INIT` stays 0, new tunnel token (or move the existing one), and `docker compose up -d`. Time it once.
4. Longer term: move the ledger to Supabase Postgres (already supported through `DATABASE_URL`) so the VM becomes stateless apart from keys.

**Status:** founder action.

### INF-07 — No monitoring or alerting — High

**Evidence:** no external uptime check is configured for the VM deployment. Nothing alerts on a failed backup, a full disk or a container restart loop. Container logs exist only as local json-file (bot: 6.6 MB, 23k lines). The OCI `unified-monitoring-agent` runs, but no alarms were found in the repo or docs. The tunnel had two QUIC reconnects in four days, which nobody would have noticed.

**Fix**
- Free external uptime monitor (Better Stack or UptimeRobot) on `https://boardman-api.playingsidequest.fun/api/health/deep` every minute, alerting to Telegram/email.
- A dead-man heartbeat for backups (`--healthcheck-url`, e.g. healthchecks.io).
- OCI Monitoring alarms on the instance: CPU > 90 % for 15 minutes, memory > 85 %, boot volume > 80 %.
- Ship logs off-box later (Better Stack/Grafana Cloud free tiers) before real money.

**Status:** script hook ready; the founder creates the accounts.

### INF-08 — Patching — Medium

**Evidence:** `/var/run/reboot-required` has existed since 2026-10-16 (`linux-image-7.0.0-1013-oracle`); the running kernel is 6.17.0-1020. unattended-upgrades covers the Ubuntu security origins only and has no automatic reboot. cloudflared 2026.10.0 is installed; 2026.10.1 is available from `pkg.cloudflare.com`, which is not in the auto-update origins, and the process runs with `--no-autoupdate`. Docker comes from Ubuntu's `docker.io` (29.1.3) and is updated by hand.

**Fix:** `harden_vm.sh` adds the cloudflared origin and an automatic reboot at 04:30 UTC (after the 03:17 backup). Containers (`restart: always`) and the tunnel (enabled unit) come back by themselves. Reboot once by hand now, at a quiet time. Patch Docker monthly.

**Status:** script ready.

### INF-09 — Deploy drift — Medium

**Evidence:** the VM checkout is at `fb90227`, 17 commits behind `origin/main` (`70a7c64`). The image was built on the VM on 2026-10-18 from unpinned dependencies. The 127.0.0.1 binding exists only because of an **untracked** `docker-compose.override.yml`.

**Fix:** the base compose now binds loopback by default (INF-13), so the override can be deleted. Deploy with a fixed procedure: `git fetch && git checkout <sha>`, `docker compose build`, `up -d`, then record the deployed SHA. Next step: build the arm64 image in CI and pull it by digest, instead of building on the production box.

**Status:** compose fixed in branch; the deploy procedure is a founder action.

### INF-10 — SSH — Medium

**Evidence:** `sshd -T` shows `permitrootlogin without-password` (root's key is limited by a forced "please login as ubuntu" command), `x11forwarding yes`, `allowagentforwarding yes`, `allowtcpforwarding yes`, `maxauthtries 6`, `logingracetime 120`, no `AllowUsers`, and RSA/ECDSA key types accepted. Password and keyboard-interactive login are already off. A second login user `opc` (uid 1000, `/bin/sh`) has the **same** authorized key as `ubuntu`. fail2ban runs the default sshd jail (10-minute bans): 1207 failures and 110 bans so far, and about 465 failed attempts in the last 24 hours.

**Fix:** `harden_vm.sh` adds a drop-in that sets `PermitRootLogin no`, password and keyboard-interactive off, `AuthenticationMethods publickey`, ed25519 keys only (it checks that an ed25519 key is present first), `AllowUsers ubuntu`, MaxAuthTries 3, LoginGraceTime 30 and all forwarding off. It is validated with `sshd -t` before reload and rolled back on failure. fail2ban gets aggressive mode, escalating bans and a recidive jail. **Note:** `AllowTcpForwarding no` also blocks `ssh -L` and OCI Bastion port-forwarding sessions; switch it to `local` if you use them.

Optional: allow port 22 only from the founder's IP in the OCI security list, and use OCI Bastion or Cloudflare Access for SSH when travelling.

**Status:** script ready.

### INF-11 — Supply chain: unpinned Python dependencies — Medium

**Evidence:** `src/backend/requirements.txt` sets only lower bounds (`fastapi>=0.141.0`, `web3>=6.15.0`, …) and there is no lockfile, so every build resolves whatever PyPI serves that day. The Dockerfiles use `python:3.12-slim` (floating) and an unpinned `pip install --upgrade pip`. The npm side is fine: lockfiles exist and CI uses `npm ci`.

**Fix (this branch)**
- `src/backend/requirements-lock.txt`: the exact 100-package set running in production, from `pip freeze` in `boardman-api`. The Dockerfiles and CI install with `-c` (constraints).
- Base image pinned to `python:3.12.15-slim-trixie`, the same Python and Debian as production. Add an `@sha256` digest when convenient. pip is pinned to 26.2.1.
- `.github/dependabot.yml` covers pip, Docker, GitHub Actions and npm, weekly and grouped.
- `tests/test_requirements_lock.py`: every direct dependency is pinned and satisfies its floor, and both Dockerfiles use the lock.
- The CI `supply-chain` job runs pip-audit on the lock and `npm audit` on the frontend. It is informational until it first passes; then remove `continue-on-error`. Known unfixable: PYSEC-2026-1325 (ecdsa via python-jose).

**Status:** fixed in branch.

### INF-12 — Compilers in the runtime image — Medium

**Evidence:** the runtime stage of `Dockerfile.akash` installs `build-essential gcc libffi-dev libssl-dev`. The image is 1.56 GB, and an attacker with code execution gets a full toolchain.

**Fix:** a new `pydeps` build stage compiles the venv, and the runtime stage copies `/app/.venv` and installs only `curl ca-certificates stockfish`. A new CI `docker` job builds the image on every PR and checks that it runs as non-root, has no `gcc`, and imports the API. The image was **not** built locally during the audit; the CI job is the proof, so check it is green before deploying.

**Status:** fixed in branch.

### INF-13 — Compose and Docker networking — Medium

**Evidence:** the base `docker-compose.yml` publishes `"8000:8000"` (all interfaces). Docker-published ports go through `FORWARD`/`DOCKER`, not `INPUT`, so host firewall rules (iptables INPUT or ufw) do not protect them. The VM is safe today only because of the untracked override plus the OCI security list. No `cap_drop` or `no-new-privileges` is set. The containers are otherwise fine: user `rematch` (999), not privileged, no Docker socket, bridge network.

**Fix**
- compose now uses `"${BOARDMAN_API_BIND:-127.0.0.1}:8000:8000"`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]` and `pids_limit: 1024`. `tests/test_compose_hardening.py` enforces this.
- `harden_vm.sh` installs a `DOCKER-USER` rule as a small systemd unit tied to `docker.service`. It drops NEW connections from the internet interface to any container, so a future `0.0.0.0` publish cannot expose a container.

**Status:** fixed in branch; script ready.

### INF-14 — GitHub Actions — Medium

**Evidence:** there is no `pull_request_target`, and `ci.yml` has `permissions: contents: read` and uses no secrets. However:
- every action was pinned by mutable tag, including the third-party `docker/*` actions;
- `docker-publish.yml` and `akash-image.yml` **both** built and pushed `Dockerfile.akash` on every push to main with `packages:write`, and nothing deploys from `docker-publish`'s image;
- checkout left the token in `.git/config` for later steps;
- there was no secret scanning, no dependency audit and no Dependabot.

**Fix:** every action is now pinned to a commit SHA with a version comment. `docker-publish.yml` is manual-only with `permissions: {}` at the top, no longer uses `docker/metadata-action`, and adds SBOM and provenance. akash-image also gets SBOM and provenance. All checkouts use `persist-credentials: false`. CI gains the `docker` and `supply-chain` jobs, the new tests cover secret and RLS regressions, and Dependabot is added.

**Founder (GitHub settings):** enable **secret scanning + push protection** (free for public repos), protect `main` (require PRs and passing CI), and restrict Actions to selected/verified actions.

**Status:** fixed in branch, plus GitHub settings.

### INF-15 — Every container gets every secret — Medium

**Evidence:** all three services load the same 122-variable `.env`. The bot does not need the owner, admin or resolver keys, the Circle entity secret, the Paystack/Paycrest secrets or the Supabase service-role key, unless the code proves otherwise. `CIRCLE_API_KEY_LIVE` and `NEW_WALLET_PRIVATE_KEY` are not read by any code under `src/`.

**Fix (design; needs per-process testing, so it was not changed blind):** `.env.common` holds non-secret configuration. `.env.api`, `.env.bot` and `.env.house` each hold only what that process reads. Add `env_file: [.env.common, .env.<svc>]` per service. Start by moving the signing keys to `.env.house`/`.env.api` only, and confirm with `grep -rn os.getenv` per entry point.

**Status:** founder/engineering action.

### INF-16 — IPv6 and stray listeners — Low

**Evidence:** the IPv4 `INPUT` chain allows established, ICMP, lo and tcp/22, then rejects everything else. The OCI security list allows only 22. But `ip6tables` `INPUT` policy is **ACCEPT** with no rules, and `rpcbind` listens on `0.0.0.0:111` and `[::]:111`. The VNIC has no global IPv6 address today, so nothing is reachable yet. Adding IPv6 to the VNIC later would expose rpcbind and anything else listening on `::`. ufw is not installed. That is correct for Oracle images (see the next paragraph).

**Why not ufw:** on Oracle's Ubuntu images, `iptables-persistent` loads Oracle's `InstanceServices` rules (boot-volume iSCSI, metadata, NTP). Installing ufw removes `iptables-persistent`. The existing iptables policy is already "only 22 inbound + all outbound", so the script keeps it and refuses `--firewall=ufw` on OCI.

**Fix:** the script writes the same policy to `/etc/iptables/rules.v6` and applies it live rule by rule. It never runs `ip6tables-restore` live, which would flush Docker's chains. It also disables rpcbind when there are no NFS mounts (there are none).

**Status:** script ready.

### INF-17 — Cloudflare tunnel — Low

**Evidence:** the token is at `/etc/cloudflared/boardman-api.token` (0600 root, 180 bytes) in a directory with mode 0700. The remotely managed ingress has exactly one rule, `boardman-api.playingsidequest.fun → http://localhost:8000`, and a catch-all `http_status:404`. There is no WARP routing and no bastion mode. cloudflared runs as **root**. systemd reports that the unit changed on disk and was not reloaded. Cloudflare Access is not configured on the hostname, which is expected for a public API.

**Fix:** the script runs `daemon-reload`. The opt-in `--harden-tunnel` runs cloudflared as a systemd `DynamicUser`, passes the token as a credential, adds a sandbox, and rolls back automatically if `/ready` does not answer within 45 s. In the Cloudflare dashboard, add rate-limiting rules for auth and money endpoints, and Cloudflare Access on any admin path.

**Status:** script (opt-in) + dashboard.

### INF-18 — Docker daemon defaults — Low

**Evidence:** there is no `/etc/docker/daemon.json`, so live-restore is off and ad-hoc containers have no log cap. The compose services do set 10 MB × 3.

**Fix:** the script merges in `log-opts` (10 MB × 5), `live-restore: true` and `no-new-privileges: true`. They take effect at the next Docker restart or reboot, or right away with `--restart-docker` (about 10 s of downtime).

**Status:** script ready.

### INF-19 — Host identity notes — Low

- The container user `rematch` is uid 999. On the host, uid 999 is `ocarun`, the Oracle Cloud Agent Run Command user, so volume files show up as owned by `ocarun`. `ocarun` cannot traverse `/var/lib/docker` (0710 root), so this is cosmetic today. A future Dockerfile could pin `useradd -u 10001` plus a one-off `chown` of the volume.
- `ubuntu` is in the `docker` group and has `NOPASSWD: ALL` sudo, which is normal for a single-operator box. It also means one stolen laptop key exposes every secret. Use a passphrase-protected or hardware-backed key (FIDO `sk-ssh-ed25519`), which the new sshd policy accepts.
- The OCI Run Command plugin can execute commands as `ocarun` from the OCI console. Protect the OCI account with MFA.

### INF-20 — Vercel/Supabase key handling — Low

`frontend/lib/supabaseAdmin.ts` uses `SUPABASE_SERVICE_ROLE_KEY` in server routes, which is correct, but **silently falls back to the anon key** if the service key is missing. Add `import 'server-only'` to that module and fail closed in production. Keep the service-role key out of Vercel *Preview* environments. Content-Security-Policy is covered by the web audit.

---

## Passed checks

- Only `22/tcp` is reachable from the internet: OCI security list plus iptables INPUT REJECT. The API (`docker-proxy`) listens on `127.0.0.1:8000` only, and cloudflared metrics on `127.0.0.1:20241`.
- SSH: `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitEmptyPasswords no`. All three accounts have locked passwords. A single ed25519 key is authorized.
- fail2ban is active. Unattended security upgrades run daily (last run 2026-10-19). AppArmor is on, and the Docker seccomp/AppArmor defaults apply.
- Containers run as non-root (`rematch`), are not privileged, add no capabilities, use no host network or PID namespace, and do not mount the Docker socket. The API has a healthcheck, and all services use `restart: always` with log rotation.
- `.env` is 0600, the tunnel token is 0600 root, and `/etc/cloudflared` is 0700.
- **Container logs (≈26k lines across all three services) contained 0 matches** for Telegram bot URLs or tokens, PEM keys, private-key assignments, Paystack/Circle keys, JWTs, bearer tokens, 64-hex strings, or PIN/password fields. The `~/build*.log` files likewise contained 0.
- `.dockerignore` excludes `.env*`, so images contain no secrets.
- No `pull_request_target`, no secrets in CI, and npm lockfiles with `npm ci`.
- Every 2026-10 Supabase migration enables RLS.

---

## Founder checklist (in order)

1. **Today:** run `supabase/verify_rls.sql` in the Supabase SQL editor, then apply `20261020120000_lock_down_legacy_grants.sql` (INF-04).
2. **Today:** rotate the Circle API key and client key, then revoke the old ones. Confirm the old Telegram token is revoked (INF-02).
3. On your laptop: `age-keygen -o ~/boardman-backup.agekey`, and store it in your password manager. Store the VM `.env` and the Circle recovery file there too (INF-05).
4. Create an off-box bucket (OCI Object Storage in another region, or R2/B2) and configure `rclone` on the VM as `ubuntu`. Create a healthchecks.io check and an uptime monitor (INF-05, INF-07).
5. On the VM, from a second SSH session:
   `sudo bash harden_vm.sh` (review the dry run), then
   `sudo bash harden_vm.sh --apply --age-recipient age1… --backup-remote <remote:path> --healthcheck-url <url> --encrypt-old-backups`.
   Open a **new** SSH session to confirm login still works before closing the old one. Reboot once at a quiet time for the pending kernel (INF-08).
6. Merge `audit/infra` after CI is green, including the new `docker` job. Deploy main to the VM, delete `docker-compose.override.yml`, and record the deployed SHA (INF-09, INF-11–14).
7. GitHub settings: secret scanning + push protection, branch protection on `main`, Actions allow-list (INF-14).
8. OCI: upgrade to PAYG with a budget alert, add a boot-volume backup policy, turn on MFA (INF-06, INF-19).
9. Before any real money: rotate agent wallets onto the keystore (INF-03), put the contract owner behind a multisig and remove `OWNER_PRIVATE_KEY`/`ADMIN_PRIVATE_KEY` from the VM, remove the resolver fallback, split env files per container, and plan KMS for the resolver key and keystore secret (INF-01, INF-15). Do a restore drill and write down the result (INF-05).

## Files in this branch

| File | Purpose |
|---|---|
| `docs/security/AUDIT_2026-10_infra.md` | This report |
| `scripts/harden_vm.sh` | Idempotent VM hardening; dry run by default, `--apply` to change |
| `supabase/migrations/20261020120000_lock_down_legacy_grants.sql` | Revokes anon grants, enables RLS, locks the balance RPCs |
| `supabase/verify_rls.sql` | Read-only check of what the anon key can reach |
| `src/backend/requirements-lock.txt` | Exact production dependency set (constraints) |
| `Dockerfile.akash`, `Dockerfile` | Pinned base, constraints install, no compilers at runtime (akash) |
| `docker-compose.yml` | Loopback bind by default, cap_drop ALL, no-new-privileges, pids limit |
| `.github/workflows/*.yml`, `.github/dependabot.yml` | SHA-pinned actions, manual-only duplicate publish, PR image build, dependency audit, Dependabot |
| `tests/test_supabase_rls.py`, `tests/test_no_secrets_in_tree.py`, `tests/test_requirements_lock.py`, `tests/test_compose_hardening.py` | Regression guards for INF-02, -04, -11, -13 |
