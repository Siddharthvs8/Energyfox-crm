# Scheduled jobs (systemd timers)

The CRM has two background jobs that must run on a schedule. On AWS these run on
the app EC2 instance via systemd timers (no extra service needed for 50 users).

| Job | Command | Cadence | What it does |
|-----|---------|---------|--------------|
| Automation queue | `process_automation_queue` | every 5 min | resumes timed automation steps, flushes queued bulk WhatsApp, fires `lead_inactive`, purges 7-day-old Trash, trims automation logs >90 days |
| Archive old leads | `archive_old_leads` | nightly 02:30 | archives terminal leads (lost / not interested / fully delivered) older than `ARCHIVE_AFTER_MONTHS` |
| Certificate backup | `deploy/backup-certs.sh` | nightly 03:15 | snapshots `certbot/conf` (certs, private keys, ACME account key, renewal config) to `/var/backups/energyfox`, keeping 30 |

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

`energyfox-certbackup.service`
```ini
[Unit]
Description=EnergyFox certificate backup
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/energyfox
ExecStart=/opt/energyfox/deploy/backup-certs.sh
```

`energyfox-certbackup.timer`
```ini
[Unit]
Description=Back up EnergyFox TLS certificates nightly

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true

[Install]
WantedBy=timers.target
```

## Enable

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now energyfox-queue.timer energyfox-archive.timer energyfox-certbackup.timer
systemctl list-timers | grep energyfox      # confirm next run times
```

## Restoring certificates

Archives are root-only (`/var/backups/energyfox`, dir `700`, files `600`) because
they contain private keys in the clear — `ls` them with `sudo`, or the glob will
not even expand.

```bash
sudo ./deploy/backup-certs.sh --verify-only /var/backups/energyfox/certbot-<ts>.tar.gz
sudo tar -xzf /var/backups/energyfox/certbot-<ts>.tar.gz -C /opt/energyfox   # restores certbot/conf
cd /opt/energyfox && docker compose restart nginx
```

Extract with `tar -xzf`, never by copying files individually: `live/` holds
symlinks into `archive/`, and flattening them breaks the next renewal. The
archive also carries the ACME account key, so a restore needs no contact with
Let's Encrypt — which matters during an incident, since only 5 certificates per
domain per week can be issued.

**This covers certificates only — not the database.** For that see the `pg_dump`
command in `EC2_DOCKER_DEPLOY.md`. Neither backup leaves the instance, so an
instance loss loses both; EBS snapshots are the fix for that.

## Plain-cron alternative

```cron
*/5 * * * *  cd /opt/energyfox && docker compose exec -T backend python manage.py process_automation_queue >> /var/log/energyfox-queue.log 2>&1
30 2 * * *   cd /opt/energyfox && docker compose exec -T backend python manage.py archive_old_leads >> /var/log/energyfox-archive.log 2>&1
```
