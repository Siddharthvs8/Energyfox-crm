# Scheduled jobs (systemd timers)

The CRM has two background jobs that must run on a schedule. On AWS these run on
the app EC2 instance via systemd timers (no extra service needed for 50 users).

| Job | Command | Cadence | What it does |
|-----|---------|---------|--------------|
| Automation queue | `process_automation_queue` | every 5 min | resumes timed automation steps, flushes queued bulk WhatsApp, fires `lead_inactive`, purges 7-day-old Trash, trims automation logs >90 days |
| Archive old leads | `archive_old_leads` | nightly 02:30 | archives terminal leads (lost / not interested / fully delivered) older than `ARCHIVE_AFTER_MONTHS` |

If you run the stack with Docker Compose, prefix the command with
`docker compose exec -T backend`. If you run the backend directly under a venv,
call `/opt/energyfox/backend/venv/bin/python manage.py <cmd>`.

## Files to drop in `/etc/systemd/system/`

`energyfox-queue.service`
```ini
[Unit]
Description=EnergyFox automation queue
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/energyfox
ExecStart=/usr/bin/docker compose exec -T backend python manage.py process_automation_queue
```

`energyfox-queue.timer`
```ini
[Unit]
Description=Run EnergyFox automation queue every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
```

`energyfox-archive.service`
```ini
[Unit]
Description=EnergyFox archive old leads
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/energyfox
ExecStart=/usr/bin/docker compose exec -T backend python manage.py archive_old_leads
```

`energyfox-archive.timer`
```ini
[Unit]
Description=Archive old EnergyFox leads nightly

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

## Enable

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now energyfox-queue.timer energyfox-archive.timer
systemctl list-timers | grep energyfox      # confirm next run times
```

## Plain-cron alternative

```cron
*/5 * * * *  cd /opt/energyfox && docker compose exec -T backend python manage.py process_automation_queue >> /var/log/energyfox-queue.log 2>&1
30 2 * * *   cd /opt/energyfox && docker compose exec -T backend python manage.py archive_old_leads >> /var/log/energyfox-archive.log 2>&1
```
