<!-- domain:INFRA | layer:asset | ssot:false | updated:2026-06-04 -->
# New-Server Hardening Checklist

Run before a host serves production traffic.

## Access
- [ ] SSH: `PasswordAuthentication no`, `PermitRootLogin no`, `AllowUsers` allow-list (drop-in file).
- [ ] `sshd -t` passes; reloaded (not restarted) with a second session open.
- [ ] Keys: ed25519, `~/.ssh` 700, `authorized_keys` 600, one key per identity.
- [ ] fail2ban (or equivalent) enabled on the sshd jail.
- [ ] A non-root deploy user with scoped `sudoers.d/` — no blanket root.

## Network
- [ ] Firewall default-deny inbound; only served ports open (`ufw`/`firewalld`).
- [ ] SSH restricted to known source CIDRs or behind a bastion.
- [ ] No unexpected listeners — `ss -ltnp` reviewed.

## Services
- [ ] Every long-running process is a systemd unit with `Restart=on-failure`.
- [ ] Services run as dedicated non-root users.
- [ ] Sandboxing on: `NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`.
- [ ] Logs go to journald; crash loops bounded with `StartLimit*`.

## Hygiene
- [ ] OS on a supported LTS (`make skills-check-versions` for the pin).
- [ ] Unattended security updates enabled.
- [ ] Permissions: dirs 750, files 640, secrets 600 — no `chmod 777` anywhere.
- [ ] `scripts/triage.sh --json` baseline captured (disk/mem/load/ports/failed).
- [ ] Backups configured as a systemd timer + restore tested.
