# AWS Deployment Guide for CRM SaaS

Your current target:

```text
Domain: zaleshunter.com
EC2 public IP: 13.53.39.220
Current DNS result checked locally: zaleshunter.com -> 13.60.99.199
```

Before deployment, update DNS so `zaleshunter.com` and `*.zaleshunter.com` point to `13.53.39.220`. The app uses tenant subdomains, so the wildcard DNS record is important.

This app is a multi-tenant Django backend plus a Next.js frontend. The repo already has Dockerfiles, so the best production AWS path is:

- **ECS Fargate** for the backend and frontend containers
- **Amazon ECR** for Docker images
- **Amazon RDS PostgreSQL** for the database
- **Application Load Balancer** for HTTPS routing
- **Route 53 + ACM** for domains and SSL
- **S3** for uploaded media files, or EFS if you want to keep filesystem storage
- **Secrets Manager or SSM Parameter Store** for environment variables
- **CloudWatch Logs** for app logs

For a quick MVP, App Runner is possible, but ECS Fargate fits this app better because it has two services, tenant subdomains, media uploads, and Django migrations.

## 1. Required Code Changes Before Production

### Frontend API base URL

`frontend/src/lib/mock-data.ts` currently builds API URLs like:

```ts
return `${protocol}://${domain}.localhost${portSuffix}`;
```

For AWS, replace this with an environment-based root domain:

```ts
export function getApiBase(domain: string): string {
  const protocol = process.env.NEXT_PUBLIC_API_PROTOCOL || 'https';
  const rootDomain = process.env.NEXT_PUBLIC_ROOT_DOMAIN || 'example.com';
  const port = process.env.NEXT_PUBLIC_API_PORT;
  const portSuffix = port ? `:${port}` : '';
  return `${protocol}://${domain}.${rootDomain}${portSuffix}`;
}

export function getPublicApiBase(): string {
  const protocol = process.env.NEXT_PUBLIC_API_PROTOCOL || 'https';
  const rootDomain = process.env.NEXT_PUBLIC_ROOT_DOMAIN || 'example.com';
  const port = process.env.NEXT_PUBLIC_API_PORT;
  const portSuffix = port ? `:${port}` : '';
  return `${protocol}://${rootDomain}${portSuffix}`;
}
```

Then set:

```env
NEXT_PUBLIC_API_PROTOCOL=https
NEXT_PUBLIC_ROOT_DOMAIN=zaleshunter.com
NEXT_PUBLIC_API_PORT=
```

### Frontend tenant middleware

`frontend/src/middleware.ts` currently has:

```ts
const rootDomains = ['localhost', 'crm.com', '127.0.0.1'];
```

Change it so production domain comes from env:

```ts
const configuredRootDomain = process.env.NEXT_PUBLIC_ROOT_DOMAIN || 'crm.com';
const rootDomains = ['localhost', '127.0.0.1', configuredRootDomain];
```

### Hardcoded local API calls

Search for `.localhost`:

```bash
rg "\.localhost|localhost:8000" frontend/src
```

At the time this guide was written, `frontend/src/app/app/[domain]/leads/[id]/page.tsx` still uses hardcoded `http://${params.domain}.localhost:8000`. Convert those calls to `getApiBase(params.domain)`.

### Django media storage

Current Django media is local:

```py
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
```

Local container media is not durable in production. Use one of these:

- Recommended: S3 with `django-storages`
- Alternative: EFS mounted into the backend ECS task

For S3, install:

```txt
django-storages[boto3]>=1.14
```

Then configure `DEFAULT_FILE_STORAGE` / Django `STORAGES` for media.

### Migrations

`backend/entrypoint.sh` runs migrations every container startup:

```sh
python manage.py migrate_schemas --shared
python manage.py migrate_schemas
```

This is okay for one backend task, but risky with multiple replicas. For production, run migrations as a one-off ECS task before deploying a new backend revision.

## 2. AWS Architecture

Use this layout:

```text
Internet
  |
Route 53 DNS
  |
ACM HTTPS certificate: yourdomain.com + *.yourdomain.com
  |
Application Load Balancer
  |-- Host: yourdomain.com          -> frontend ECS service, port 3000
  |-- Host: *.yourdomain.com        -> frontend ECS service, port 3000
  |-- Path /api/* or /api-public/*  -> backend ECS service, port 8000
  |-- Path /media/*                 -> S3/CloudFront or backend if using EFS

ECS Fargate private subnets
  |-- frontend container
  |-- backend container

RDS PostgreSQL private subnets
S3 bucket for media uploads
Secrets Manager for app secrets
CloudWatch Logs
```

## 3. Create AWS Resources

Choose a region, for example Mumbai:

```bash
set AWS_REGION=ap-south-1
```

### ECR repositories

```bash
aws ecr create-repository --repository-name crm-saas-backend --region ap-south-1
aws ecr create-repository --repository-name crm-saas-frontend --region ap-south-1
```

Login to ECR:

```bash
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com
```

Build and push backend:

```bash
docker build -t crm-saas-backend ./backend
docker tag crm-saas-backend:latest ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/crm-saas-backend:latest
docker push ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/crm-saas-backend:latest
```

Build and push frontend:

```bash
docker build ^
  --build-arg NEXT_PUBLIC_API_PROTOCOL=https ^
  --build-arg NEXT_PUBLIC_ROOT_DOMAIN=zaleshunter.com ^
  --build-arg NEXT_PUBLIC_API_PORT= ^
  -t crm-saas-frontend ./frontend

docker tag crm-saas-frontend:latest ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/crm-saas-frontend:latest
docker push ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/crm-saas-frontend:latest
```

On Linux/macOS, replace `^` line continuations with `\`.

### RDS PostgreSQL

Create PostgreSQL 15 or newer.

Recommended starter settings:

- Engine: PostgreSQL
- Instance: `db.t4g.micro` or `db.t4g.small` for MVP
- Storage: 20-50 GB gp3
- Public access: No
- VPC: same VPC as ECS
- Security group: allow PostgreSQL 5432 only from ECS backend security group
- Backups: enabled, at least 7 days

Keep these values:

```env
DB_NAME=crm_saas_db
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=your-rds-endpoint.rds.amazonaws.com
DB_PORT=5432
```

### S3 media bucket

Create:

```bash
aws s3 mb s3://crm-saas-prod-media --region ap-south-1
```

Keep it private. Serve files through signed URLs or CloudFront if needed.

## 4. Production Environment Variables

Backend ECS task:

```env
DEBUG=False
SECRET_KEY=generate-a-long-random-secret
ALLOWED_HOSTS=zaleshunter.com,.zaleshunter.com
CORS_ALLOWED_ORIGINS=https://zaleshunter.com
DB_NAME=crm_saas_db
DB_USER=...
DB_PASSWORD=...
DB_HOST=...
DB_PORT=5432
RAZORPAY_KEY_ID=...
RAZORPAY_KEY_SECRET=...
GEMINI_API_KEY=...
AIRTEL_CUSTOMER_ID=...
AIRTEL_AUTH_KEY=...
AIRTEL_PHONE_NUMBER=...
AIRTEL_BRIDGE_BASE_URL=https://zaleshunter.com
```

Frontend ECS task:

```env
NODE_ENV=production
NEXT_PUBLIC_API_PROTOCOL=https
NEXT_PUBLIC_ROOT_DOMAIN=zaleshunter.com
NEXT_PUBLIC_API_PORT=
```

Store secrets in Secrets Manager or SSM Parameter Store, not directly in the task definition JSON.

## 5. ECS Fargate Setup

Create one ECS cluster:

```bash
aws ecs create-cluster --cluster-name crm-saas-prod --region ap-south-1
```

Create two task definitions:

- `crm-saas-backend`
  - Image: backend ECR image
  - Port: 8000
  - CPU/memory starter: 0.5 vCPU / 1 GB
  - Health check path: `/api/health/`
  - Environment/secrets: backend env above

- `crm-saas-frontend`
  - Image: frontend ECR image
  - Port: 3000
  - CPU/memory starter: 0.25-0.5 vCPU / 0.5-1 GB
  - Health check path: `/`
  - Environment: frontend env above

Run both services in private subnets behind an Application Load Balancer.

## 6. Load Balancer Rules

Create HTTPS listener on port 443 using an ACM certificate for:

```text
yourdomain.com
*.yourdomain.com
```

Listener rules:

```text
IF path is /api/* OR /api-public/*
THEN forward to backend target group port 8000

IF host is yourdomain.com OR *.yourdomain.com
THEN forward to frontend target group port 3000
```

If media is still served by Django/EFS:

```text
IF path is /media/*
THEN forward to backend target group port 8000
```

If using S3/CloudFront for media, do not send `/media/*` to backend.

## 7. DNS

In Route 53 hosted zone for `yourdomain.com`:

```text
yourdomain.com      A/AAAA alias -> Application Load Balancer
*.yourdomain.com    A/AAAA alias -> Application Load Balancer
```

This wildcard is important because Django tenants use domains like:

```text
alpha.yourdomain.com
testfirm.yourdomain.com
```

Tenant records in the Django `customers_domain` table must also use production domains, not `.localhost`.

## 8. Run Migrations

Before the first deploy, run a one-off ECS task with the backend image:

```bash
python manage.py migrate_schemas --shared
python manage.py migrate_schemas
```

Then create your first tenant/domain:

```bash
python manage.py shell
```

Example:

```py
from customers.models import Client, Domain

tenant = Client(schema_name="alpha", name="Alpha CRM")
tenant.save()

Domain.objects.create(
    domain="alpha.yourdomain.com",
    tenant=tenant,
    is_primary=True,
)
```

## 9. Security Groups

ALB security group:

- Inbound: 80, 443 from internet
- Outbound: frontend/backend task security groups

Frontend ECS security group:

- Inbound: 3000 only from ALB security group
- Outbound: internet/NAT as needed

Backend ECS security group:

- Inbound: 8000 only from ALB security group
- Outbound: RDS, S3, external APIs

RDS security group:

- Inbound: 5432 only from backend ECS security group

## 10. Deployment Flow

After code changes:

```bash
docker build -t crm-saas-backend ./backend
docker tag crm-saas-backend:latest ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/crm-saas-backend:latest
docker push ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/crm-saas-backend:latest

docker build --build-arg NEXT_PUBLIC_API_PROTOCOL=https --build-arg NEXT_PUBLIC_ROOT_DOMAIN=zaleshunter.com --build-arg NEXT_PUBLIC_API_PORT= -t crm-saas-frontend ./frontend
docker tag crm-saas-frontend:latest ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/crm-saas-frontend:latest
docker push ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/crm-saas-frontend:latest

aws ecs update-service --cluster crm-saas-prod --service crm-saas-backend --force-new-deployment --region ap-south-1
aws ecs update-service --cluster crm-saas-prod --service crm-saas-frontend --force-new-deployment --region ap-south-1
```

## 11. Post-Deploy Checks

Check backend:

```bash
curl https://zaleshunter.com/api/health/
curl https://alpha.zaleshunter.com/api/health/
```

Check frontend:

```bash
https://zaleshunter.com
https://alpha.zaleshunter.com
```

Check logs:

```bash
aws logs tail /ecs/crm-saas-backend --follow --region ap-south-1
aws logs tail /ecs/crm-saas-frontend --follow --region ap-south-1
```

## 12. Minimum Production Checklist

- `DEBUG=False`
- Strong `SECRET_KEY`
- RDS is private
- Database backups enabled
- ALB uses HTTPS
- ACM certificate includes wildcard domain
- `ALLOWED_HOSTS` includes root and wildcard domain
- CORS includes frontend origin
- Media files use S3 or EFS
- Migrations are run before deployment, not by many replicas at once
- CloudWatch logs enabled
- AWS budget alert configured
- Tenant domains changed from `.localhost` to production domains
