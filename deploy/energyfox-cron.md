# Scheduled jobs (systemd timers)

The CRM has two background jobs that must run on a schedule. On AWS these run on
the app EC2 instance via systemd timers (no extra service needed for 50 users).

| Job | Command | Cadence | What it does |
|-----|---------|---------|--------------|
| Automation queue | `process_automation_queue` | every 5 min | resumes timed automation steps, flushes queued bulk WhatsApp, fires `lead_inactive`, purges 7-day-old Trash, trims automation logs >90 days |
| Meta lead sync | `sync_meta_leads` | hourly | pulls Meta Lead Ads leads for any integration whose 12 hours are up — the safety net for leads the webhook never delivered |
| Archive old leads | `archive_old_leads` | nightly 02:30 | archives terminal leads (lost / not interested / fully delivered) older than `ARCHIVE_AFTER_MONTHS` |
| Database backup | `deploy/backup-db.sh` | nightly 03:00 | `pg_dump` of the CRM database, gzipped to `/var/backups/energyfox`, keeping 30 |
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

`energyfox-meta-sync.service`
```ini
[Unit]
Description=EnergyFox Meta lead sync
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/energyfox
ExecStart=/usr/bin/docker compose exec -T backend python manage.py sync_meta_leads
```

`energyfox-meta-sync.timer`
```ini
[Unit]
Description=Pull Meta leads for any integration due a sync

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

Run **hourly**, not twelve-hourly. The command decides due-ness per integration
from its own `last_synced_at`, so an hourly timer still pulls each page once
every twelve hours — and a page whose turn was missed (host down, deploy,
container restarting) is picked up within the hour instead of waiting another
twelve. `Persistent=true` covers a host that was off at the scheduled moment.

Pressing **Sync Now** in the CRM moves the same clock, so a manual sync is never
followed minutes later by an automatic one. To change the cadence, pass
`--hours N`; to pull everything regardless, `--force`. `--dry-run` prints what
is due without calling Meta.

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

`energyfox-dbbackup.service`
```ini
[Unit]
Description=EnergyFox database backup
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/energyfox
ExecStart=/opt/energyfox/deploy/backup-db.sh
```

`energyfox-dbbackup.timer`
```ini
[Unit]
Description=Back up the EnergyFox database nightly

[Timer]
OnCalendar=*-*-* 03:00:00
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
sudo systemctl enable --now energyfox-queue.timer energyfox-archive.timer \
                            energyfox-meta-sync.timer \
                            energyfox-dbbackup.timer energyfox-certbackup.timer
systemctl list-timers | grep energyfox      # confirm next run times
```

## Restoring the database

Check what you have, then prove the archive actually loads before trusting it —
`--restore-test` restores into a scratch database, compares the table count
against production, and drops it again:

```bash
sudo ls -lh /var/backups/energyfox/db-*.sql.gz
sudo ./deploy/backup-db.sh --restore-test                    # newest archive
sudo ./deploy/backup-db.sh --restore-test /var/backups/energyfox/db-<ts>.sql.gz
```

To actually restore, load into an **empty** database. The dump carries no `DROP`
statements, so replaying it over a populated database gives "already exists"
errors on every object rather than replacing anything:

```bash
cd /opt/energyfox
docker compose stop backend                                     # stop writes first
docker compose exec -T db dropdb   -U energyfox --if-exists energyfox_crm
docker compose exec -T db createdb -U energyfox energyfox_crm
zcat /var/backups/energyfox/db-<ts>.sql.gz \
  | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U energyfox -d energyfox_crm
docker compose start backend
```

`ON_ERROR_STOP=1` matters — without it psql reports success after skipping
statements that failed, leaving a half-restored database that looks fine.

Every `docker compose exec` here needs `-T`, and inside a script also
`</dev/null`, or the client eats the rest of the script off stdin.

**Uploads are not included.** `pg_dump` covers the database only; user uploads
live in the `backend_media` Docker volume. That volume is nearly empty today,
but it will not stay that way once invoices and documents are attached.

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
0 * * * *    cd /opt/energyfox && docker compose exec -T backend python manage.py sync_meta_leads >> /var/log/energyfox-meta-sync.log 2>&1
30 2 * * *   cd /opt/energyfox && docker compose exec -T backend python manage.py archive_old_leads >> /var/log/energyfox-archive.log 2>&1
```
