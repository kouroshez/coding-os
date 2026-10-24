<!-- domain:INFRA | layer:reference | ssot:true | updated:2026-06-04 -->
# SSH Hardening

> P: Lock SSH to keys + allow-list, survive package upgrades, resist brute force.
> R: Provisioning a server, exposing SSH to the internet, or reviewing access.
> S: App-layer auth (JWT/OAuth) — that's [auth-patterns](../../auth-patterns/SKILL.md).
> N: [SKILL.md](../SKILL.md), [systemd-and-services.md](systemd-and-services.md)

> Nav: [Skill](../SKILL.md)

## Use a drop-in, never the main file

```bash
# /etc/ssh/sshd_config.d/10-hardening.conf
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
KbdInteractiveAuthentication no
MaxAuthTries 3
MaxSessions 4
LoginGraceTime 20
AllowUsers deploy
X11Forwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
```

Drop-ins in `sshd_config.d/` survive `apt upgrade` (which may replace the main
file). Always validate before reloading:

```bash
sshd -t && systemctl reload sshd      # -t = syntax check; reload keeps your session
```

`reload` (not `restart`) keeps existing sessions — so a mistake doesn't lock you
out before you can fix it. Keep a second session open while changing SSH.

## Keys done right

```bash
ssh-keygen -t ed25519 -C "deploy@host"     # ed25519 > rsa: smaller, faster, modern
ssh-copy-id deploy@host                      # appends to ~/.ssh/authorized_keys
chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys
```

`authorized_keys` must be `600`, `~/.ssh` `700`, owned by the user — sshd
refuses keys on loose permissions. Rotate keys on offboarding; one key per
person/machine so you can revoke precisely.

## Brute-force + exposure

- **fail2ban** — bans IPs after N failed auths (`/etc/fail2ban/jail.local`, `sshd` jail).
- **Non-standard port** — cuts log noise, not real security (don't rely on it alone).
- **Bastion / jump host** — production hosts have no public SSH; reach them via one audited `ProxyJump` bastion.
- **Firewall** — `ufw allow from <office-cidr> to any port 22` restricts source.

## Verify the lockdown

```bash
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no deploy@host
# MUST fail with "Permission denied (publickey)" — proves passwords are off.
```
