---
name: linux-sysadmin
tier: infra
domain: [infra]
description: Operate and harden Linux hosts — SSH, systemd services, users/permissions, package management, networking, firewall, log triage, and resource inspection. Use when configuring a server, writing a systemd unit, hardening SSH, debugging "the box is slow / a port won't bind / a service won't start", setting up a firewall, or triaging a host under load. Targets Debian/Ubuntu + RHEL/Fedora families. Triggers — "ssh", "systemd", "the server", "permission denied", "port in use", "service won't start", "harden the box", "set up the VPS", "linux". Pairs with deployment-cicd (containers/pipelines), incident-response (host on fire), security-web (app-side hardening), shell-scripting (the automation).
globs: ""
paths: []
last_reviewed: "2026-06-04"
versions_ref: versions.json
---

# Linux System Administration

A server is a contract with production: it stays up, it's reachable only how you intend, and when it misbehaves you can see why in one pass. This skill is host-level operation + hardening. Containers and pipelines belong to [deployment-cicd](../deployment-cicd/SKILL.md); the incident *process* to [incident-response](../incident-response/SKILL.md); this is the box itself.

> Triage a host in one compact report (disk, mem, load, failed units, ports):
> `bash scripts/triage.sh --json`

## SSH — the front door, hardened

```bash
# /etc/ssh/sshd_config.d/10-hardening.conf  (drop-in, survives package upgrades)
PermitRootLogin no
PasswordAuthentication no            # keys only — the single biggest win
PubkeyAuthentication yes
KbdInteractiveAuthentication no
MaxAuthTries 3
AllowUsers deploy                    # allow-list, not everyone
```

```bash
# Wrong — edits the main file, lost on upgrade, no syntax check before reload
vi /etc/ssh/sshd_config && systemctl restart sshd     # locks you out if typo'd

# Correct — drop-in + validate + reload (keeps your current session alive)
sshd -t && systemctl reload sshd                       # -t aborts on bad config
```

Keys not passwords, root login off, an `AllowUsers` allow-list, `fail2ban` for brute-force. Never restart sshd before `sshd -t` passes — a typo + restart locks you out of a remote box. Full hardening → [references/ssh-hardening.md](references/ssh-hardening.md).

## systemd — services that restart themselves

```ini
# /etc/systemd/system/api.service
[Unit]
Description=API service
After=network-online.target

[Service]
ExecStart=/usr/local/bin/api --port 8080
Restart=on-failure
RestartSec=2
User=api                             # never run a service as root
NoNewPrivileges=true                 # cheap hardening
ProtectSystem=strict                 # read-only /usr, /boot, /etc

[Install]
WantedBy=multi-user.target
```

`systemctl daemon-reload` after editing a unit, then `enable --now`. Read failures with `systemctl status api` + `journalctl -u api -e --no-pager`. A service with no `Restart=` dies silently on the first crash. Recipes → [references/systemd-and-services.md](references/systemd-and-services.md).

## Permissions — least privilege, by default

```bash
# Wrong — 777 "to make it work" is an open door
chmod -R 777 /var/www

# Correct — owner writes, group reads, world nothing; dirs need +x to enter
chown -R deploy:www-data /var/www
find /var/www -type d -exec chmod 750 {} \;
find /var/www -type f -exec chmod 640 {} \;
```

`chmod 777` is never the answer — it's "I don't know who needs access" written as a vulnerability. Files `640`, dirs `750`, secrets `600` owned by the service user. `sudo` for specific commands via `/etc/sudoers.d/`, not blanket root.

## The host-triage reflex (slow box / won't bind / OOM)

| Symptom | First command |
|---|---|
| slow / high load | `uptime` (load avg vs core count), `top`/`htop` |
| out of memory | `free -h`, `dmesg | grep -i oom` (the OOM killer logs here) |
| disk full | `df -h`, `du -xhd1 / | sort -h | tail` |
| port won't bind | `ss -ltnp | grep :8080` (who holds it) |
| service down | `systemctl status X`, `journalctl -u X -e` |
| can't reach it | `ss -ltn`, then firewall: `ufw status` / `firewall-cmd --list-all` |

`scripts/triage.sh` runs the safe read-only subset of these in one shot and emits a compact summary — read three lines instead of running six commands.

## Packages & firewall (Debian/Ubuntu ↔ RHEL/Fedora)

| | Debian/Ubuntu | RHEL/Fedora |
|---|---|---|
| install | `apt install` | `dnf install` |
| update index | `apt update` | (dnf auto) |
| firewall | `ufw allow 443/tcp` | `firewall-cmd --add-service=https --permanent` |
| service logs | `journalctl` | `journalctl` |

Default-deny inbound, allow only the ports you serve. Pin OS versions in [versions.json](versions.json); LTS in production, not the latest interim release.

## Anti-patterns (reject on sight)

- `chmod 777` / `PasswordAuthentication yes` / `PermitRootLogin yes` → all open doors.
- Restarting `sshd` without `sshd -t` first → remote lockout.
- Editing `/etc/ssh/sshd_config` directly instead of a `sshd_config.d/` drop-in.
- A long-running daemon launched from a shell / `nohup` instead of a systemd unit (no restart, no logs, dies on logout).
- Running a service as `root` "because permissions" → fix the ownership, drop the privilege.
- `curl … | sudo bash` from an unverified source → read it first.

## See also

- [references/ssh-hardening.md](references/ssh-hardening.md) — keys, drop-ins, fail2ban, bastion.
- [references/systemd-and-services.md](references/systemd-and-services.md) — units, timers, sandboxing, journald.
- [assets/hardening-checklist.md](assets/hardening-checklist.md) — the new-server ship gate.
- [deployment-cicd](../deployment-cicd/SKILL.md) · [incident-response](../incident-response/SKILL.md) · [shell-scripting](../shell-scripting/SKILL.md).
