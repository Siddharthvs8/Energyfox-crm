# EnergyFox CRM — AWS Architecture (≈50 active users)

Sizing note: 50 concurrent internal users is a **small** workload. The goal is a
cheap, durable, low-ops setup — not a large distributed cluster. One app instance
plus a managed database and S3 is the right size; scale up (not out) if needed.

```
                         Route 53  (energyfox domain)
                             │
                        ┌────┴─────┐
                        │  ACM TLS │  (free HTTPS cert)
                        └────┬─────┘
                    Application Load Balancer  (HTTPS :443 → :80)
                             │
        ┌────────────────────┴────────────────────┐
        │            EC2  t3.medium (1 instance)   │
        │   Docker Compose:                        │
        │     nginx  ── / ──►  Next.js (frontend)  │
        │            ── /api,/media,/static ─┐     │
        │                                    ▼     │
        │                     gunicorn (Django, 5 workers)
        └───────┬───────────────────────────┬──────┘
                │                            │
        ┌───────▼────────┐          ┌────────▼─────────┐
        │  RDS Postgres  │          │       S3         │
        │  db.t3.small   │          │  uploaded docs / │
        │  Multi-AZ opt. │          │  media (durable) │
        │  auto-backups  │          └──────────────────┘
        └────────────────┘
```

## Components

| Layer | Service | Size | Why |
|-------|---------|------|-----|
| DNS + TLS | Route 53 + ACM | — | HTTPS, free managed cert |
| Ingress | Application Load Balancer | — | TLS termination, health checks, easy cert rotation. (Skip it and put nginx on :443 with Certbot if you want to shave cost.) |
| App | EC2 `t3.medium` (2 vCPU / 4 GB) | 1 | Runs the whole Docker Compose stack. Handles 50 users comfortably. `t3.large` if you also run heavy PDF/AI work on-box. |
| Database | RDS PostgreSQL `db.t3.small` | 1 (Multi-AZ optional) | Managed backups, point-in-time restore, no DB on the app disk. Enable storage autoscaling + Performance Insights. |
| Media | S3 bucket | — | Uploaded documents survive instance replacement. Enabled by setting `AWS_STORAGE_BUCKET_NAME` (see below). |
| Static | WhiteNoise (in-app) | — | Already configured; no separate service. Optionally front with CloudFront. |
| Scheduler | systemd timers on the EC2 host | — | Runs `process_automation_queue` and `archive_old_leads` (see `deploy/energyfox-cron.md`). |

Rough monthly cost (Mumbai, on-demand): EC2 t3.medium ≈ $30, RDS db.t3.small ≈
$30 (×2 for Multi-AZ), ALB ≈ $18, S3 a few dollars. ~$80–110/mo. Reserved
instances cut EC2/RDS ~40%.

## Why not more?

- **No autoscaling group / multiple app nodes.** 50 users don't need it, and the
  app keeps JWTs client-side (stateless auth), so you *can* add nodes later
  behind the ALB with no code change — media is on S3 and the DB is external.
- **No ElastiCache/Redis.** No caching or Celery is required at this size; the
  scheduled jobs are cron-style management commands.

## Gunicorn sizing

`entrypoint.sh` runs `(2×vCPU)+1 = 5` workers × 4 threads (tunable via
`WEB_CONCURRENCY` / `GUNICORN_THREADS`). `--max-requests 1000` recycles workers
to bound memory. This serves ~50 users with large headroom.

Postgres `CONN_MAX_AGE=600` keeps connections warm. With 5 workers you use ≤ ~5
DB connections at a time — well under `db.t3.small`'s limit.

---

## Data strategy — "new data fast, old data archived"

The active working set is kept small so list/board/dashboard queries stay fast as
years of history accumulate:

1. **Archive (leads).** Terminal leads — lost, not interested, or fully delivered
   (converted + project complete + fully paid) — older than `ARCHIVE_AFTER_MONTHS`
   (default 3) are flagged `is_archived` by the nightly `archive_old_leads` job.
   Archived leads are **excluded from every hot path** (the Leads list, badge
   counts) and viewable on demand via the Leads **Archived** toggle, or restored.
   They are never deleted.

2. **Composite indexes** on the hot query paths (added in migration `0044`):
   - `(is_trashed, is_archived, -created_at)` — the default active-leads list
   - `(is_archived, status, -created_at)` — status filters/boards
   - `(assigned_to, is_archived)`, `(bde, is_archived)` — per-owner views

   So even before archiving kicks in, the active queries use an index that
   already skips trashed/archived rows.

3. **Trash purge.** Deleted leads are soft-deleted for 7 days then permanently
   removed (existing behaviour) — bounds the table.

4. **Log trimming.** `process_automation_queue` deletes automation logs older
   than 90 days (pure telemetry) so that table doesn't grow unbounded.

5. **RDS.** Point-in-time restore + automated snapshots are your archive of record
   for compliance; storage autoscaling absorbs growth.

If the DB ever gets genuinely large (years in), the next step is moving archived
rows to a separate `leads_archive` table or an S3/Athena cold store — but at 50
users that's far off; the flag + indexes are enough for a long time.

---

## Media on S3 (durable uploads)

Uploaded documents (Aadhaar, PAN, purchase orders, generated PDFs, logo, etc.)
**must not** sit on the instance disk in production. Set these env vars on the
backend and django-storages routes all media to S3:

```
AWS_STORAGE_BUCKET_NAME=energyfox-crm-media
AWS_S3_REGION_NAME=ap-south-1
# Prefer an EC2 instance role over keys. Only set these if not using a role:
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...
# Optional CloudFront in front of the bucket:
# AWS_S3_CUSTOM_DOMAIN=dxxxx.cloudfront.net
```

Unset ⇒ media stays on the local filesystem (dev default). No code change needed.
The IAM role/policy needs `s3:GetObject/PutObject/DeleteObject/ListBucket` on that
bucket.

---

## Deploy checklist

1. **RDS**: create `db.t3.small` Postgres, enable automated backups + storage
   autoscaling. Note host/user/password.
2. **S3**: create the media bucket; attach an IAM role to the EC2 instance with
   access to it.
3. **EC2**: `t3.medium`, Docker + Compose. Clone the repo to `/opt/energyfox`.
4. **`backend/.env`** (production):
   ```
   DEBUG=False
   SECRET_KEY=<64-char random>
   ALLOWED_HOSTS=crm.energyfox.in,<alb-dns>
   CSRF_TRUSTED_ORIGINS=https://crm.energyfox.in
   CORS_ALLOWED_ORIGINS=https://crm.energyfox.in
   DB_HOST=<rds-endpoint>  DB_NAME=energyfox_crm  DB_USER=...  DB_PASSWORD=...
   AWS_STORAGE_BUCKET_NAME=energyfox-crm-media
   AWS_S3_REGION_NAME=ap-south-1
   EMAIL_HOST=...  EMAIL_HOST_USER=...  EMAIL_HOST_PASSWORD=...
   ```
5. **Build & run**: `docker compose up -d --build` (migrations + collectstatic run
   automatically via `entrypoint.sh`).
6. **First run**: `docker compose exec backend python manage.py createsuperuser`.
7. **Scheduler**: install the systemd timers from `deploy/energyfox-cron.md`.
8. **ALB + ACM + Route 53**: point the domain at the ALB, attach the cert, target
   the instance on :80.

## Security posture (already in code)

- `DEBUG=False` flips on HSTS, secure cookies, `SECURE_PROXY_SSL_HEADER`,
  nosniff, `X-Frame-Options: DENY` (see `config/settings.py`).
- CORS is whitelisted from env in production (not `*`).
- DRF throttling: 300/min per user, 30/min anon.
- JWT: 12 h access, 7 d rotating refresh.
- Put RDS and the app in a VPC; the DB security group should allow :5432 **only**
  from the app instance's security group. S3 access via instance role, no keys.
