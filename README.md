# EnergyFox CRM

A custom, single-company CRM for **EnergyFox** (solar). Built with **Django REST Framework** +
**Next.js**. This is an internal product for EnergyFox only — there is no multi-tenancy, no
subscription billing, and no public SaaS surface.

## Features

- **Leads** — full CRUD, filtering/search, custom statuses, activity timeline, invoice attachment on enrollment
- **Tasks** — board + list, priorities, assignments, due dates
- **Calls** — Voxbay / Exotel click-to-call, webhooks, recordings
- **Campaigns**, **Automations**, **WhatsApp** messaging, **Inventory** (products, vendors, quotes, sales/purchase orders)
- **AI Manager** — targets, daily/monthly performance, notifications, meetings
- **Team** — roles (Admin / General Manager / Manager / Agent), leaderboards, performance
- **Org Settings** — one place to configure telephony (Voxbay/Exotel), WhatsApp, logo, and custom lead statuses

## Architecture

- **Backend**: Django 4.2 + DRF, JWT auth, a single PostgreSQL database (standard, no `django-tenants`)
- **Frontend**: Next.js 16 (App Router) + Tailwind CSS 4 + TypeScript, served from flat routes (`/leads`, `/tasks`, …)
- **Org config**: a singleton `organization.OrgSettings` row (read via `organization.utils.get_org_settings()`)

## Quick Start

### 1. Database
```bash
docker-compose up -d db        # or use a local PostgreSQL
```
Create the database named in `.env` (`DB_NAME`, default `energyfox_crm`).

### 2. Backend
```bash
cd backend
python -m venv venv
# Windows: .\venv\Scripts\activate   |   macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```
- App: http://localhost:3000  (redirects to **/login**)
- Backend API: http://localhost:8000
- Django admin: http://localhost:8000/sys-admin/

Set `NEXT_PUBLIC_API_BASE` (e.g. `http://localhost:8000`) if the frontend and backend are not same-origin.

## Configuration

All runtime config lives in `.env` (see `.env.example`). Org-level integration settings
(telephony, WhatsApp, logo, custom lead statuses) are edited in-app under **Settings**, or in the
Django admin under **Organization Settings**.

## Project Structure

```
backend/
  config/         # settings + single URLconf
  organization/   # OrgSettings singleton (replaces the old tenant model)
  users/ leads/ tasks/ calls/ campaigns/ automations/ inventory/ messaging/ ai_manager/
frontend/
  src/app/
    (crm)/        # the CRM (sidebar layout + all pages) at flat routes
    login/        # login page
docker-compose.yml, nginx.conf
```
