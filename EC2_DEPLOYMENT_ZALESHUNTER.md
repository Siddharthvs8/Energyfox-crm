# EC2 Deployment for zaleshunter.com

Use this if you want to deploy directly on your existing EC2 instance:

```text
Domain: zaleshunter.com
EC2 public IP: 13.53.39.220
```

Important: local DNS currently resolves `zaleshunter.com` to `13.60.99.199`, not `13.53.39.220`. Fix DNS first.

## 1. DNS

In your DNS provider, set:

```text
Type    Name    Value
A       @       13.53.39.220
A       *       13.53.39.220
CNAME   www     zaleshunter.com
```

Remove the old A record pointing to `13.60.99.199`.

Why wildcard matters: this app uses tenant domains like:

```text
alpha.zaleshunter.com
demo.zaleshunter.com
```

## 2. EC2 Security Group

Allow inbound:

```text
22/tcp   your IP only
80/tcp   0.0.0.0/0
443/tcp  0.0.0.0/0
```

Do not expose 3000, 8000, or 5432 publicly if Nginx is handling traffic.

## 3. Install Server Packages

SSH into EC2:

```bash
ssh -i your-key.pem ubuntu@13.53.39.220
```

Install Docker:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git nginx certbot python3-certbot-nginx
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
```

Log out and SSH back in so Docker group permissions apply.

Install Docker Compose plugin if missing:

```bash
docker compose version
```

If that fails:

```bash
sudo apt install -y docker-compose-plugin
```

## 4. Copy Code to Server

Option A, Git:

```bash
git clone YOUR_REPO_URL crm-saas
cd crm-saas
```

Option B, upload files with SCP:

```bash
scp -i your-key.pem -r crm-saas ubuntu@13.53.39.220:/home/ubuntu/crm-saas
```

## 5. Backend Environment

Create `backend/.env`:

```env
DEBUG=False
SECRET_KEY=replace-with-a-long-random-secret
ALLOWED_HOSTS=zaleshunter.com,.zaleshunter.com,13.53.39.220
CSRF_TRUSTED_ORIGINS=https://zaleshunter.com,https://*.zaleshunter.com
CORS_ALLOWED_ORIGINS=https://zaleshunter.com
CORS_ALLOWED_ORIGIN_REGEXES=^https://.*\.zaleshunter\.com$

DB_NAME=crm_saas_db
DB_USER=postgres
DB_PASSWORD=use-a-strong-password
DB_HOST=db
DB_PORT=5432

RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
GEMINI_API_KEY=
AIRTEL_CUSTOMER_ID=
AIRTEL_AUTH_KEY=
AIRTEL_PHONE_NUMBER=
AIRTEL_BRIDGE_BASE_URL=https://zaleshunter.com
```

For quick EC2 deployment, the included Docker Compose PostgreSQL service is acceptable. For serious production, move PostgreSQL to RDS.

## 6. Frontend Build Environment

Create a root `.env` file used by Docker Compose:

```env
DB_USER=postgres
DB_PASSWORD=use-a-strong-password
DB_NAME=crm_saas_db

NEXT_PUBLIC_API_PROTOCOL=https
NEXT_PUBLIC_ROOT_DOMAIN=zaleshunter.com
NEXT_PUBLIC_API_PORT=
```

The frontend Dockerfile has been updated to accept `NEXT_PUBLIC_ROOT_DOMAIN`.

## 7. Nginx Container

`docker-compose.yml` now includes the `nginx` service by default. Backend, frontend, and PostgreSQL ports are bound to `127.0.0.1` only; public traffic should enter through Nginx on port 80.

The repo `nginx.conf` now uses:

```text
server_name *.zaleshunter.com zaleshunter.com;
```

It also routes both `/api/` and `/api-public/` to Django.

## 8. Start the App

```bash
docker compose up -d --build
docker compose ps
```

Check logs:

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f nginx
```

Check health:

```bash
curl http://13.53.39.220/health
curl http://zaleshunter.com/health
curl http://zaleshunter.com/api/health/
```

## 9. HTTPS

The cleanest EC2 approach is host-level Nginx + Certbot, but if you use the Nginx Docker container, you need to add certificate volumes and SSL config manually.

Simpler host-level SSL path:

1. Stop Docker Nginx from binding port 80.
2. Expose frontend/backend only locally, or keep them mapped to `127.0.0.1`.
3. Use host Nginx as the public reverse proxy.
4. Run:

```bash
sudo certbot --nginx -d zaleshunter.com -d "*.zaleshunter.com"
```

Wildcard certificates usually require DNS validation. If Certbot asks for DNS TXT records, add them in your DNS provider.

For a non-wildcard first launch:

```bash
sudo certbot --nginx -d zaleshunter.com -d www.zaleshunter.com
```

Then add wildcard SSL later.

## 10. Create Production Tenant

After containers are running:

```bash
docker compose exec backend python manage.py shell
```

Then:

```py
from customers.models import Client, Domain

tenant = Client(schema_name="alpha", name="Alpha CRM")
tenant.save()

Domain.objects.create(
    domain="alpha.zaleshunter.com",
    tenant=tenant,
    is_primary=True,
)
```

Then visit:

```text
https://alpha.zaleshunter.com
```

## 11. Current Verification From Local Machine

Latest local checks:

```text
zaleshunter.com resolves to 13.60.99.199
www.zaleshunter.com CNAMEs to zaleshunter.com
http://13.53.39.220 did not respond
http://zaleshunter.com timed out
```

So the next concrete actions are:

1. Update DNS to `13.53.39.220`.
2. Open ports 80 and 443 in EC2 security group.
3. Deploy with Docker Compose.
4. Add SSL.
