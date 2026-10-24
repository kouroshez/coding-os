<!-- domain:INFRA | layer:reference | ssot:true | updated:2026-06-04 -->
# systemd — Units, Timers, Sandboxing, Logs

> P: Run a process as a managed service that restarts, logs, and drops privilege.
> R: Deploying any long-running process to a Linux host.
> S: Orchestrating containers — that's [deployment-cicd](../../deployment-cicd/SKILL.md).
> N: [SKILL.md](../SKILL.md), [ssh-hardening.md](ssh-hardening.md)

> Nav: [Skill](../SKILL.md)

## A service unit, hardened

```ini
# /etc/systemd/system/api.service
[Unit]
Description=API service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/api --port 8080
Restart=on-failure
RestartSec=2
User=api
Group=api
# sandboxing — cheap, high value
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/api

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload          # ALWAYS after editing a unit file
systemctl enable --now api       # start now + on boot
systemctl status api             # state + last log lines
journalctl -u api -e --no-pager  # full logs, jump to end
```

The sandbox directives (`ProtectSystem`, `PrivateTmp`, `NoNewPrivileges`) cost
nothing and contain a compromised service to its own data. Run as a dedicated
`User=`, never root.

## Timers replace cron

```ini
# backup.timer  (+ a matching backup.service with the command)
[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true        # run on next boot if the host was off at 03:00

[Install]
WantedBy=timers.target
```

`systemctl enable --now backup.timer`; inspect with `systemctl list-timers`.
Timers log to journald (cron's output vanishes) and share the service's
sandboxing — prefer them over crontab for anything that matters.

## Reading failures fast

| Question | Command |
|---|---|
| Why did it die? | `journalctl -u api -e` (look for the exit + the lines before) |
| Is it flapping? | `systemctl status api` → "Active: ... (Result: ...)" + restart count |
| What failed at boot? | `systemctl --failed` |
| Resource limits hit? | `systemctl show api -p MemoryCurrent,TasksCurrent` |
| Tail live | `journalctl -u api -f` |

A crash-looping service shows a rising restart counter; add `StartLimitBurst` +
`StartLimitIntervalSec` to stop infinite restart storms, and fix the root cause
in the logs rather than raising the limit.
