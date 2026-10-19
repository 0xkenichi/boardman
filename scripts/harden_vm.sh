#!/usr/bin/env bash
# Harden the Boardman production VM (Oracle Cloud A1, Ubuntu 24.04).
#
# Written for the 2026-10 infra audit (docs/security/AUDIT_2026-10_infra.md).
# Idempotent. DRY RUN BY DEFAULT: prints every change it would make and makes
# none. Re-run with --apply to change the box. Safe to run repeatedly.
#
# Run it ON the VM, from a second SSH session you keep open until you have
# proved a fresh login still works:
#
#   scp scripts/harden_vm.sh ubuntu@150.230.112.144:
#   ssh ubuntu@150.230.112.144 'sudo bash harden_vm.sh'                 # dry run
#   ssh ubuntu@150.230.112.144 'sudo bash harden_vm.sh --apply \
#        --age-recipient age1yourpublickey... \
#        [--backup-remote oci:boardman-backups] [--healthcheck-url https://hc-ping.com/<uuid>]'
#
# Steps (all on by default; pick a subset with --only a,b,c):
#   ssh        sshd drop-in: no passwords, no keyboard-interactive, no root,
#              ed25519 keys only, AllowUsers ubuntu, no forwarding, MaxAuthTries 3
#   firewall   IPv4: verify the OCI iptables policy (only 22 inbound).
#              IPv6: same policy (today IPv6 INPUT is ACCEPT-all; harmless only
#              while the VNIC has no IPv6 address)
#   dockerfw   DOCKER-USER rule: drop NEW connections from the internet to any
#              container, so a future "8000:8000" cannot bypass the firewall
#   fail2ban   sshd jail (aggressive, incremental bans) + recidive jail
#   upgrades   unattended-upgrades: also patch cloudflared, auto-reboot 04:30 UTC
#   docker     /etc/docker/daemon.json: log rotation, live-restore,
#              no-new-privileges (takes effect on the next dockerd restart;
#              add --restart-docker to restart now: ~10 s of downtime)
#   services   disable rpcbind (listening on 0.0.0.0:111, unused), daemon-reload
#   backup     encrypt nightly backups with age to an offline key, verify the
#              SQLite snapshot, optional off-box copy (rclone), dead-man ping,
#              lock down ~/backups permissions
#   tunnel     OPT-IN (--harden-tunnel): run cloudflared as a DynamicUser with
#              the token passed as a systemd credential; auto-rollback if the
#              tunnel is not ready within 45 s
#
# Deliberately NOT done here (needs a human decision, see the audit report):
# rotating secrets, moving the contract-owner key off the box, splitting the
# .env per container, rebooting for the pending kernel, enabling ufw on OCI.
set -euo pipefail

APPLY=0
ONLY=""
FIREWALL_MODE="auto"
RESTART_DOCKER=0
HARDEN_TUNNEL=0
ENCRYPT_OLD=0
AGE_RECIPIENT="${AGE_RECIPIENT:-}"
BACKUP_REMOTE="${BACKUP_REMOTE:-}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-}"
APP_USER="${APP_USER:-ubuntu}"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6 || true)"
APP_HOME="${APP_HOME:-/home/$APP_USER}"
BACKUP_DIR="$APP_HOME/backups"
REBOOT_TIME="${REBOOT_TIME:-04:30}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
CHANGES=0

usage() { sed -n '2,40p' "$0"; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --dry-run) APPLY=0 ;;
    --only) ONLY="$2"; shift ;;
    --only=*) ONLY="${1#*=}" ;;
    --firewall) FIREWALL_MODE="$2"; shift ;;
    --firewall=*) FIREWALL_MODE="${1#*=}" ;;
    --restart-docker) RESTART_DOCKER=1 ;;
    --harden-tunnel) HARDEN_TUNNEL=1 ;;
    --encrypt-old-backups) ENCRYPT_OLD=1 ;;
    --age-recipient) AGE_RECIPIENT="$2"; shift ;;
    --age-recipient=*) AGE_RECIPIENT="${1#*=}" ;;
    --backup-remote) BACKUP_REMOTE="$2"; shift ;;
    --backup-remote=*) BACKUP_REMOTE="${1#*=}" ;;
    --healthcheck-url) HEALTHCHECK_URL="$2"; shift ;;
    --healthcheck-url=*) HEALTHCHECK_URL="${1#*=}" ;;
    -h|--help) usage 0 ;;
    *) echo "unknown option: $1" >&2; usage 2 ;;
  esac
  shift
done

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root (sudo bash $0 ...)" >&2
  exit 1
fi

say()  { printf '%s\n' "$*"; }
head_() { printf '\n== %s\n' "$*"; }
would() { CHANGES=$((CHANGES + 1)); if [ "$APPLY" = 1 ]; then say "  CHANGE: $*"; else say "  WOULD: $*"; fi; }
ok()   { say "  ok: $*"; }
warn() { say "  WARN: $*"; }
want() { [ -z "$ONLY" ] && return 0; case ",$ONLY," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }

# ensure_file PATH MODE OWNER  (content on stdin). Writes only if different;
# keeps a timestamped .bak of what it replaces. Returns 0 if it changed.
ensure_file() {
  local path="$1" mode="$2" owner="$3" tmp
  tmp="$(mktemp)"
  cat > "$tmp"
  if [ -f "$path" ] && cmp -s "$tmp" "$path"; then
    local cur_mode cur_owner
    cur_mode="$(stat -c %a "$path")"; cur_owner="$(stat -c %U:%G "$path")"
    if [ "$cur_mode" = "$mode" ] && [ "$cur_owner" = "$owner" ]; then
      ok "$path up to date"; rm -f "$tmp"; return 1
    fi
  fi
  would "write $path (mode $mode, $owner)"
  if [ -f "$path" ]; then diff -u "$path" "$tmp" | sed 's/^/      /' | head -60 || true
  else sed 's/^/      + /' "$tmp" | head -60; fi
  if [ "$APPLY" = 1 ]; then
    mkdir -p "$(dirname "$path")"
    [ -f "$path" ] && cp -p "$path" "$path.bak.$TS"
    install -m "$mode" -o "${owner%%:*}" -g "${owner##*:}" "$tmp" "$path"
  fi
  rm -f "$tmp"
  return 0
}

run() { if [ "$APPLY" = 1 ]; then "$@"; fi; }

say "Boardman VM hardening — $(hostname) — $(date -u)"
if [ "$APPLY" = 1 ]; then say "MODE: APPLY (changes will be made)"; else say "MODE: DRY RUN (nothing will change; add --apply)"; fi

# ─────────────────────────────────────────────────────────────────────────────
if want ssh; then
  head_ "ssh"
  ak="$APP_HOME/.ssh/authorized_keys"
  if ! grep -qE '^(ssh-ed25519|sk-ssh-ed25519@openssh.com) ' "$ak" 2>/dev/null; then
    warn "$ak has no ed25519 key; refusing to restrict key types (would lock you out)"
    ALGOS=""
  else
    ALGOS="PubkeyAcceptedAlgorithms ssh-ed25519,ssh-ed25519-cert-v01@openssh.com,sk-ssh-ed25519@openssh.com,sk-ssh-ed25519-cert-v01@openssh.com"
  fi
  # 10- sorts before 50-cloud-init.conf / 60-cloudimg-settings.conf; sshd keeps
  # the FIRST value it reads, so these win.
  if ensure_file /etc/ssh/sshd_config.d/10-boardman-hardening.conf 644 root:root <<EOF
# Managed by scripts/harden_vm.sh (Boardman infra audit 2026-10). Do not edit by hand.
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PubkeyAuthentication yes
AuthenticationMethods publickey
${ALGOS}
AllowUsers ${APP_USER}
MaxAuthTries 3
LoginGraceTime 30
MaxStartups 10:30:60
ClientAliveInterval 300
ClientAliveCountMax 2
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
AllowStreamLocalForwarding no
PermitTunnel no
GatewayPorts no
PermitUserEnvironment no
EOF
  then
    if [ "$APPLY" = 1 ]; then
      if sshd -t; then
        systemctl reload ssh.service
        say "  sshd reloaded. KEEP THIS SESSION OPEN and test: ssh -o BatchMode=yes $APP_USER@<vm> true"
      else
        warn "sshd -t failed; restoring previous config"
        if [ -f "/etc/ssh/sshd_config.d/10-boardman-hardening.conf.bak.$TS" ]; then
          mv "/etc/ssh/sshd_config.d/10-boardman-hardening.conf.bak.$TS" /etc/ssh/sshd_config.d/10-boardman-hardening.conf
        else
          rm -f /etc/ssh/sshd_config.d/10-boardman-hardening.conf
        fi
        exit 1
      fi
    fi
  fi
  if [ "$APPLY" = 1 ]; then
    say "  effective: $(sshd -T 2>/dev/null | grep -E '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication|allowusers|maxauthtries) ' | tr '\n' ' ')"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
OCI=0
iptables -S InstanceServices >/dev/null 2>&1 && OCI=1
if want firewall; then
  head_ "firewall"
  if [ "$FIREWALL_MODE" = "auto" ]; then
    if [ "$OCI" = 1 ]; then FIREWALL_MODE=iptables; else FIREWALL_MODE=ufw; fi
  fi
  if [ "$FIREWALL_MODE" = "ufw" ] && [ "$OCI" = 1 ]; then
    warn "ufw requested on an Oracle Cloud image. Installing ufw removes iptables-persistent,"
    warn "which carries Oracle's InstanceServices rules (boot-volume iSCSI, metadata, NTP)."
    warn "The existing iptables policy already allows only TCP 22 inbound; using it instead."
    FIREWALL_MODE=iptables
  fi
  if [ "$FIREWALL_MODE" = "ufw" ]; then
    if ! command -v ufw >/dev/null; then would "apt-get install ufw"; run apt-get install -y -qq ufw; fi
    if ! ufw status 2>/dev/null | grep -q "Status: active"; then
      would "ufw default deny incoming; default allow outgoing; allow 22/tcp; enable"
      run ufw default deny incoming; run ufw default allow outgoing
      run ufw allow 22/tcp; run ufw --force enable
    else ok "ufw active"; ufw status verbose | sed 's/^/      /'; fi
  else
    # IPv4: verify, do not rewrite (Oracle's rules.v4 is correct and boot-critical).
    if iptables -C INPUT -p tcp -m state --state NEW -m tcp --dport 22 -j ACCEPT 2>/dev/null \
       && iptables -S INPUT | tail -1 | grep -q -- '-j REJECT'; then
      ok "IPv4 INPUT: established, icmp, lo, tcp/22, then REJECT"
    else
      warn "IPv4 INPUT is not the expected 'only 22' policy:"; iptables -S INPUT | sed 's/^/      /'
    fi
    extra="$(iptables -S INPUT | grep -E -- '--dport' | grep -v -- '--dport 22 ' || true)"
    [ -n "$extra" ] && warn "extra open IPv4 ports: $extra"
    # IPv6: persist an equivalent policy for boot, and apply it live rule by rule
    # (never ip6tables-restore live: it would flush Docker's ip6 chains).
    ensure_file /etc/iptables/rules.v6 644 root:root <<'EOF' || true
# Managed by scripts/harden_vm.sh — same policy as rules.v4: only SSH inbound.
*filter
:INPUT DROP [0:0]
:FORWARD DROP [0:0]
:OUTPUT ACCEPT [0:0]
-A INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A INPUT -i lo -j ACCEPT
-A INPUT -p ipv6-icmp -j ACCEPT
-A INPUT -p tcp -m conntrack --ctstate NEW -m tcp --dport 22 -j ACCEPT
COMMIT
EOF
    for rule in "-m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT" "-i lo -j ACCEPT" \
                "-p ipv6-icmp -j ACCEPT" "-p tcp -m conntrack --ctstate NEW -m tcp --dport 22 -j ACCEPT"; do
      # shellcheck disable=SC2086
      if ! ip6tables -C INPUT $rule 2>/dev/null; then would "ip6tables -A INPUT $rule"; run ip6tables -A INPUT $rule; fi
    done
    if ip6tables -S INPUT | head -1 | grep -q -- '-P INPUT ACCEPT'; then
      would "ip6tables -P INPUT DROP"; run ip6tables -P INPUT DROP
    else ok "IPv6 INPUT policy is DROP"; fi
    if ip -6 addr show scope global | grep -q inet6; then
      warn "this VM has a global IPv6 address — the IPv6 step matters now"
    fi
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
if want dockerfw; then
  head_ "dockerfw (DOCKER-USER)"
  EXT_IF="$(ip route show default | awk '{print $5; exit}')"
  ensure_file /usr/local/sbin/boardman-docker-user-fw 755 root:root <<EOF || true
#!/bin/sh
# Managed by scripts/harden_vm.sh. Docker-published ports skip the INPUT chain;
# DOCKER-USER is the one place a host rule applies to them. Drop every NEW
# connection that arrives from the internet ($EXT_IF) for a container. Replies
# to the containers' own outbound connections are ESTABLISHED and pass.
set -e
iptables -C DOCKER-USER -i $EXT_IF -m conntrack --ctstate NEW -j DROP 2>/dev/null \\
  || iptables -I DOCKER-USER 1 -i $EXT_IF -m conntrack --ctstate NEW -j DROP
EOF
  ensure_file /etc/systemd/system/boardman-docker-user-fw.service 644 root:root <<'EOF' && run systemctl daemon-reload || true
# Managed by scripts/harden_vm.sh
[Unit]
Description=Boardman: block internet ingress to Docker containers (DOCKER-USER)
After=docker.service
BindsTo=docker.service
PartOf=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/boardman-docker-user-fw

[Install]
WantedBy=docker.service
EOF
  if ! systemctl is-enabled boardman-docker-user-fw.service >/dev/null 2>&1; then
    would "systemctl enable --now boardman-docker-user-fw.service"
    run systemctl enable --now boardman-docker-user-fw.service
  else ok "boardman-docker-user-fw enabled"; fi
  if [ "$APPLY" = 1 ] && iptables -S DOCKER-USER 2>/dev/null | grep -q -- "-i $EXT_IF -m conntrack --ctstate NEW -j DROP"; then
    ok "DOCKER-USER drops NEW from $EXT_IF"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
if want fail2ban; then
  head_ "fail2ban"
  if ! command -v fail2ban-client >/dev/null; then would "apt-get install fail2ban"; run apt-get install -y -qq fail2ban; fi
  if ensure_file /etc/fail2ban/jail.d/boardman.local 644 root:root <<'EOF'
# Managed by scripts/harden_vm.sh
[DEFAULT]
backend = systemd
findtime = 10m
maxretry = 4
bantime = 1h
bantime.increment = true
bantime.maxtime = 4w

[sshd]
enabled = true
mode = aggressive

# Repeat offenders across jails get a week.
[recidive]
enabled = true
backend = auto
logpath = /var/log/fail2ban.log
findtime = 1d
maxretry = 3
bantime = 1w
EOF
  then
    if [ "$APPLY" = 1 ]; then
      fail2ban-client -t >/dev/null && systemctl restart fail2ban
      sleep 2; fail2ban-client status | sed 's/^/      /'
    fi
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
if want upgrades; then
  head_ "unattended-upgrades"
  if ! dpkg -s unattended-upgrades >/dev/null 2>&1; then would "apt-get install unattended-upgrades"; run apt-get install -y -qq unattended-upgrades; fi
  ensure_file /etc/apt/apt.conf.d/20auto-upgrades 644 root:root <<'EOF' || true
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
  ensure_file /etc/apt/apt.conf.d/52boardman-unattended 644 root:root <<EOF || true
// Managed by scripts/harden_vm.sh (Boardman infra audit 2026-10)
// apt merges lists across files: this ADDS the cloudflared repo to the
// security origins from 50unattended-upgrades.
Unattended-Upgrade::Origins-Pattern {
        "origin=cloudflared,label=cloudflared";
};
// Kernel and libc fixes only take effect after a reboot. The nightly backup
// runs at 03:17 UTC; reboot after it. Containers and the tunnel come back by
// themselves (restart: always, systemd enabled).
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "true";
Unattended-Upgrade::Automatic-Reboot-Time "${REBOOT_TIME}";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-New-Unused-Dependencies "true";
Unattended-Upgrade::SyslogEnable "true";
EOF
  if [ -f /var/run/reboot-required ]; then
    warn "reboot pending since $(stat -c %y /var/run/reboot-required | cut -d. -f1) for: $(tr '\n' ' ' < /var/run/reboot-required.pkgs 2>/dev/null)"
    warn "running kernel $(uname -r); the auto-reboot window will take it at ${REBOOT_TIME} UTC once --apply'd"
  fi
  if [ "$APPLY" = 1 ]; then
    say "  effective: $(apt-config dump | grep -E 'Unattended-Upgrade::(Automatic-Reboot|Origins-Pattern)' | tr '\n' ' ')"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
if want docker; then
  head_ "docker daemon"
  want_json='{"log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "5"}, "live-restore": true, "no-new-privileges": true}'
  merged_file="$(mktemp)"
  python3 - "$want_json" > "$merged_file" <<'PY'
import json, os, sys
want = json.loads(sys.argv[1])
path = "/etc/docker/daemon.json"
cur = {}
if os.path.exists(path):
    with open(path) as f:
        cur = json.load(f)
cur.update({k: v for k, v in want.items() if k != "log-opts"})
cur["log-opts"] = {**cur.get("log-opts", {}), **want["log-opts"]}
print(json.dumps(cur, indent=2, sort_keys=True))
PY
  if ensure_file /etc/docker/daemon.json 644 root:root < "$merged_file"; then
    if [ "$APPLY" = 1 ]; then
      if dockerd --validate --config-file /etc/docker/daemon.json >/dev/null 2>&1; then ok "daemon.json valid"
      else warn "dockerd --validate rejected daemon.json; restoring"; [ -f "/etc/docker/daemon.json.bak.$TS" ] && mv "/etc/docker/daemon.json.bak.$TS" /etc/docker/daemon.json || rm -f /etc/docker/daemon.json; exit 1; fi
      if [ "$RESTART_DOCKER" = 1 ]; then
        say "  restarting docker (containers restart; ~10 s API downtime)"
        systemctl restart docker
        sleep 15; docker ps --format '    {{.Names}} {{.Status}}'
      else
        say "  takes effect at the next docker restart or reboot (or re-run with --restart-docker)"
      fi
    fi
  fi
  rm -f "$merged_file"
fi

# ─────────────────────────────────────────────────────────────────────────────
if want services; then
  head_ "services"
  if systemctl is-enabled rpcbind.socket >/dev/null 2>&1 || systemctl is-active rpcbind.service >/dev/null 2>&1; then
    if [ -n "$(findmnt -n -t nfs,nfs4 2>/dev/null)" ]; then
      warn "NFS mounts present; leaving rpcbind alone"
    else
      would "systemctl disable --now rpcbind.socket rpcbind.service (listening on 0.0.0.0:111, no NFS mounts)"
      run systemctl disable --now rpcbind.socket rpcbind.service
    fi
  else ok "rpcbind disabled"; fi
  if systemctl show boardman-tunnel.service -p NeedDaemonReload 2>/dev/null | grep -q yes; then
    would "systemctl daemon-reload (boardman-tunnel.service changed on disk)"
    run systemctl daemon-reload
  fi
  for f in "$APP_HOME/boardman/.env"; do
    [ -f "$f" ] || continue
    m="$(stat -c %a "$f")"
    if [ "$m" != "600" ]; then would "chmod 600 $f (is $m)"; run chmod 600 "$f"; else ok "$f is 600"; fi
  done
  if [ -f /etc/cloudflared/boardman-api.token ]; then
    m="$(stat -c %a /etc/cloudflared/boardman-api.token)"
    if [ "$m" != "600" ]; then would "chmod 600 tunnel token"; run chmod 600 /etc/cloudflared/boardman-api.token; else ok "tunnel token is 600 root"; fi
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
if want backup; then
  head_ "backup"
  if [ -d "$BACKUP_DIR" ]; then
    m="$(stat -c %a "$BACKUP_DIR")"
    if [ "$m" != "700" ]; then would "chmod 700 $BACKUP_DIR (is $m)"; run chmod 700 "$BACKUP_DIR"; else ok "$BACKUP_DIR is 700"; fi
    n="$(find "$BACKUP_DIR" -maxdepth 1 -name 'boardman-*.tgz' -perm /044 | wc -l)"
    if [ "$n" -gt 0 ]; then would "chmod 600 $n group/world-readable plaintext backups"; run find "$BACKUP_DIR" -maxdepth 1 -name 'boardman-*.tgz' -exec chmod 600 {} +; fi
  fi
  if [ -z "$AGE_RECIPIENT" ]; then
    warn "no --age-recipient: backups stay UNENCRYPTED. On your laptop (not the VM):"
    warn "  age-keygen -o ~/boardman-backup.agekey   # keep offline + in your password manager"
    warn "  then pass the printed public key (age1...) as --age-recipient"
  else
    case "$AGE_RECIPIENT" in age1*) ;; *) echo "--age-recipient must be an age public key (age1...)" >&2; exit 2 ;; esac
    if ! command -v age >/dev/null; then would "apt-get install age"; run apt-get install -y -qq age; fi
    if [ -n "$BACKUP_REMOTE" ] && ! command -v rclone >/dev/null; then would "apt-get install rclone"; run apt-get install -y -qq rclone; fi
    ensure_file /etc/boardman-backup.env 640 "root:$APP_USER" <<EOF || true
# Managed by scripts/harden_vm.sh. Public values only — no secrets here.
AGE_RECIPIENT=$AGE_RECIPIENT
# rclone remote:path for the off-box copy (configure with: rclone config, as $APP_USER).
# Empty = local only (NOT a real backup: a lost VM takes the backups with it).
BACKUP_REMOTE=$BACKUP_REMOTE
# Dead-man switch (healthchecks.io / Better Stack heartbeat). Empty = no ping.
HEALTHCHECK_URL=$HEALTHCHECK_URL
KEEP_DAYS=14
EOF
    ensure_file "$APP_HOME/backup_boardman.sh" 750 "$APP_USER:$APP_USER" <<'EOF' || true
#!/bin/sh
# Nightly Boardman backup (managed by scripts/harden_vm.sh; cron: 17 3 * * *).
# 1. consistent SQLite snapshot + the rest of /data/agentic (snap.py, read-only mount)
# 2. integrity_check on the snapshot before anything else
# 3. age-encrypt to the founder's OFFLINE key; the plaintext never stays on disk
# 4. optional off-box copy (rclone) and a dead-man ping on success or failure
set -eu
umask 077
. /etc/boardman-backup.env
OUT="$HOME/backups"; STAGE="$OUT/.staging"
mkdir -p "$STAGE"; chmod 700 "$OUT" "$STAGE"
ping_hc() { [ -n "${HEALTHCHECK_URL:-}" ] && curl -fsS -m 10 --retry 3 -o /dev/null "$HEALTHCHECK_URL$1" || true; }
trap 'rm -rf "$STAGE"/*; ping_hc /fail' EXIT
docker run --rm --network none --user 0 --entrypoint python3 \
  -v boardman-data:/data:ro -v "$STAGE":/out -v "$HOME/snap.py":/snap.py:ro \
  boardman:latest /snap.py >/dev/null
TGZ="$(ls -1t "$STAGE"/boardman-*.tgz | head -1)"
NAME="$(basename "$TGZ")"
mkdir -p "$STAGE/check"
tar -xzf "$TGZ" -C "$STAGE/check" boardman.sqlite3
[ "$(sqlite3 "$STAGE/check/boardman.sqlite3" 'PRAGMA integrity_check;')" = "ok" ] || { echo "integrity_check failed for $NAME" >&2; exit 1; }
age -r "$AGE_RECIPIENT" -o "$OUT/$NAME.age" "$TGZ"
( cd "$OUT" && sha256sum "$NAME.age" > "$NAME.age.sha256" )
rm -rf "$STAGE"/*
if [ -n "${BACKUP_REMOTE:-}" ]; then
  rclone copy --immutable "$OUT/$NAME.age" "$BACKUP_REMOTE/"
  rclone copy --immutable "$OUT/$NAME.age.sha256" "$BACKUP_REMOTE/"
fi
find "$OUT" -maxdepth 1 -name 'boardman-*.tgz.age*' -mtime +"${KEEP_DAYS:-14}" -delete
# Plaintext archives from before encryption age out on the old 14-day rule.
find "$OUT" -maxdepth 1 -name 'boardman-*.tgz' -mtime +"${KEEP_DAYS:-14}" -delete
trap - EXIT
ping_hc ""
echo "ok $NAME.age $(stat -c %s "$OUT/$NAME.age") bytes${BACKUP_REMOTE:+ -> $BACKUP_REMOTE}"
EOF
    if [ "$ENCRYPT_OLD" = 1 ]; then
      for f in "$BACKUP_DIR"/boardman-*.tgz; do
        [ -f "$f" ] || continue
        would "encrypt $(basename "$f") -> .age and remove the plaintext"
        if [ "$APPLY" = 1 ]; then
          age -r "$AGE_RECIPIENT" -o "$f.age" "$f" && chown "$APP_USER:$APP_USER" "$f.age" && chmod 600 "$f.age" && rm -f "$f"
        fi
      done
    else
      n="$(find "$BACKUP_DIR" -maxdepth 1 -name 'boardman-*.tgz' 2>/dev/null | wc -l)"
      [ "$n" -gt 0 ] && warn "$n older plaintext backups remain (contain 27 plaintext agent keys); add --encrypt-old-backups"
    fi
    if ! crontab -u "$APP_USER" -l 2>/dev/null | grep -q backup_boardman.sh; then
      would "add cron: 17 3 * * * sg docker -c $APP_HOME/backup_boardman.sh"
      if [ "$APPLY" = 1 ]; then
        ( crontab -u "$APP_USER" -l 2>/dev/null; echo "17 3 * * * /usr/bin/sg docker -c $APP_HOME/backup_boardman.sh >> $BACKUP_DIR/backup.log 2>&1" ) | crontab -u "$APP_USER" -
      fi
    else ok "backup cron present"; fi
    [ -z "$BACKUP_REMOTE" ] && warn "no --backup-remote: backups stay on this VM only"
    [ -z "$HEALTHCHECK_URL" ] && warn "no --healthcheck-url: a silently failing backup will go unnoticed"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
if want tunnel && [ "$HARDEN_TUNNEL" = 1 ]; then
  head_ "tunnel (opt-in)"
  DROPIN=/etc/systemd/system/boardman-tunnel.service.d/10-hardening.conf
  if ensure_file "$DROPIN" 644 root:root <<'EOF'
# Managed by scripts/harden_vm.sh. cloudflared ran as root with the token
# readable by it; now it runs as a throwaway user and gets the token as a
# systemd credential it can read but not keep.
[Service]
DynamicUser=yes
LoadCredential=token:/etc/cloudflared/boardman-api.token
ExecStart=
ExecStart=/usr/bin/cloudflared --no-autoupdate --metrics 127.0.0.1:20241 tunnel run --token-file %d/token
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectClock=yes
ProtectHostname=yes
RestrictSUIDSGID=yes
RestrictNamespaces=yes
RestrictRealtime=yes
LockPersonality=yes
SystemCallArchitectures=native
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
EOF
  then
    if [ "$APPLY" = 1 ]; then
      systemctl daemon-reload; systemctl restart boardman-tunnel.service
      ready=0
      for _ in $(seq 1 45); do
        if curl -fsS -m 2 http://127.0.0.1:20241/ready >/dev/null 2>&1; then ready=1; break; fi
        sleep 1
      done
      if [ "$ready" = 1 ]; then ok "tunnel ready under DynamicUser"
      else
        warn "tunnel not ready in 45 s — rolling back"
        rm -f "$DROPIN"; systemctl daemon-reload; systemctl restart boardman-tunnel.service
        exit 1
      fi
    fi
  fi
elif want tunnel; then
  head_ "tunnel"
  say "  skipped (opt-in: --harden-tunnel). cloudflared runs as root today."
fi

# ─────────────────────────────────────────────────────────────────────────────
head_ "summary"
if [ "$APPLY" = 1 ]; then say "  $CHANGES change(s) applied."
else say "  $CHANGES change(s) would be made. Re-run with --apply to make them."; fi
say "  Not automated (see docs/security/AUDIT_2026-10_infra.md): secret rotation,"
say "  contract-owner key off the box, per-container env files, reboot for the pending kernel."
