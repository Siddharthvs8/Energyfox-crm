"""
Import leads from a CSV exported from the EnergyFox lead sheet.

Expected columns (header row, case/spacing-insensitive):

    First Name, Last name, Email ID, Phone Number, Place, Product,
    Deal Value, Source, Status, Assigned to, Notes, Task

Mapping notes:
  - "Place"        -> Lead.company
  - "Product"      -> matched to a Product by name (created if missing, unless --no-create-products)
  - "Deal Value"   -> Lead.value (currency symbols / commas are stripped)
  - "Status"       -> normalized to a valid lead status (standard + org custom); falls back to 'new'
  - "Assigned to"  -> matched to a User by username / email / full name; left blank if not found
  - "Task"         -> creates a Task linked to the lead (assignee = the lead's assignee)

Usage:
    python manage.py import_leads leads.csv
    python manage.py import_leads leads.csv --dry-run
    python manage.py import_leads leads.csv --update          # update existing leads (matched by phone)
    python manage.py import_leads leads.csv --no-create-products
"""
import csv
import re
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from leads.models import Lead, Product
from tasks.models import Task
from users.models import User
from organization.utils import get_org_settings


# CSV header (lowercased, trimmed) -> logical field key
HEADER_ALIASES = {
    'first name': 'first_name',
    'last name': 'last_name', 'lastname': 'last_name',
    'email id': 'email', 'email': 'email', 'email address': 'email',
    'phone number': 'phone', 'phone': 'phone', 'mobile': 'phone', 'contact': 'phone',
    'place': 'place', 'location': 'place', 'city': 'place',
    'product': 'product',
    'deal value': 'value', 'value': 'value', 'amount': 'value',
    'source': 'source',
    'status': 'status',
    'assigned to': 'assigned_to', 'assigned': 'assigned_to', 'agent': 'assigned_to',
    'notes': 'notes', 'note': 'notes', 'remarks': 'notes',
    'task': 'task',
}


def _last10(num):
    digits = re.sub(r'\D', '', num or '')
    return digits[-10:] if len(digits) >= 10 else digits


def _parse_value(raw):
    if not raw:
        return Decimal('0')
    cleaned = re.sub(r'[^\d.\-]', '', str(raw))  # strip ₹, Rs, commas, spaces, etc.
    if not cleaned or cleaned in ('-', '.'):
        return Decimal('0')
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal('0')


class Command(BaseCommand):
    help = 'Import leads from a CSV file (see module docstring for the expected columns).'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Path to the CSV file')
        parser.add_argument('--dry-run', action='store_true',
                            help='Parse and report, but do not write to the database')
        parser.add_argument('--update', action='store_true',
                            help='Update existing leads matched by phone (default: skip duplicates)')
        parser.add_argument('--no-create-products', action='store_true',
                            help='Do not auto-create Products that are not found by name')

    def handle(self, *args, **opts):
        path = opts['path']
        dry_run = opts['dry_run']
        do_update = opts['update']
        create_products = not opts['no_create_products']

        # ── Build the set of valid statuses (standard + org custom) ──
        status_lookup = {}  # normalized -> canonical value
        for value, label in Lead.status_choices:
            status_lookup[self._norm_status(value)] = value
            status_lookup[self._norm_status(label)] = value
        for cs in (get_org_settings().custom_lead_statuses or []):
            if isinstance(cs, dict) and cs.get('value'):
                status_lookup[self._norm_status(cs['value'])] = cs['value']
                if cs.get('label'):
                    status_lookup[self._norm_status(cs['label'])] = cs['value']

        try:
            f = open(path, newline='', encoding='utf-8-sig')
        except OSError as e:
            raise CommandError(f'Could not open {path}: {e}')

        created = updated = skipped = tasks_created = 0
        warnings = []

        with f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise CommandError('CSV appears to be empty (no header row).')

            # Map the file's headers to logical keys
            colmap = {}
            for raw_header in reader.fieldnames:
                key = HEADER_ALIASES.get((raw_header or '').strip().lower())
                if key:
                    colmap[key] = raw_header
            if 'first_name' not in colmap:
                raise CommandError(
                    "Required 'First Name' column not found. Headers seen: "
                    + ', '.join(reader.fieldnames)
                )

            def cell(row, key):
                col = colmap.get(key)
                return (row.get(col) or '').strip() if col else ''

            with transaction.atomic():
                for i, row in enumerate(reader, start=2):  # row 1 is the header
                    first_name = cell(row, 'first_name')
                    if not first_name:
                        skipped += 1
                        continue

                    phone = cell(row, 'phone')
                    last_name = cell(row, 'last_name')
                    email = cell(row, 'email')
                    place = cell(row, 'place')
                    notes = cell(row, 'notes')

                    # Status
                    raw_status = cell(row, 'status')
                    status = status_lookup.get(self._norm_status(raw_status), 'new')
                    if raw_status and self._norm_status(raw_status) not in status_lookup:
                        warnings.append(f'Row {i}: unknown status "{raw_status}" -> defaulted to "new".')

                    # Source
                    raw_source = cell(row, 'source')
                    source = re.sub(r'\s+', '_', raw_source.strip().lower()) if raw_source else 'manual'

                    # Product (match by name, optionally create)
                    product = None
                    pname = cell(row, 'product')
                    if pname:
                        product = Product.objects.filter(name__iexact=pname).first()
                        if not product:
                            if create_products and not dry_run:
                                product = Product.objects.create(name=pname)
                            elif create_products:
                                pass  # would be created on a real run
                            else:
                                warnings.append(f'Row {i}: product "{pname}" not found (skipped product).')

                    # Assigned-to user
                    assignee = None
                    aname = cell(row, 'assigned_to')
                    if aname:
                        assignee = self._resolve_user(aname)
                        if not assignee:
                            warnings.append(f'Row {i}: user "{aname}" not found (left unassigned).')

                    fields = {
                        'first_name': first_name,
                        'last_name': last_name or None,
                        'email': email or None,
                        'phone': phone or None,
                        'company': place or None,
                        'value': _parse_value(cell(row, 'value')),
                        'source': source,
                        'status': status,
                        'notes': notes or None,
                        'assigned_to': assignee,
                        'product': product,
                    }

                    # Dedupe by phone (last 10 digits)
                    existing = None
                    tail = _last10(phone)
                    if tail:
                        existing = Lead.objects.filter(phone__endswith=tail).first()

                    if existing and not do_update:
                        skipped += 1
                        continue

                    lead = None
                    if existing and do_update:
                        if not dry_run:
                            for k, v in fields.items():
                                setattr(existing, k, v)
                            existing.save()
                        lead = existing
                        updated += 1
                    else:
                        if not dry_run:
                            lead = Lead.objects.create(**fields)
                        created += 1

                    # Task (optional)
                    task_title = cell(row, 'task')
                    if task_title and not dry_run and lead is not None:
                        Task.objects.create(title=task_title, lead=lead, assignee=assignee)
                        tasks_created += 1
                    elif task_title:
                        tasks_created += 1

                if dry_run:
                    transaction.set_rollback(True)

        for w in warnings[:50]:
            self.stdout.write(self.style.WARNING(w))
        if len(warnings) > 50:
            self.stdout.write(self.style.WARNING(f'... and {len(warnings) - 50} more warnings.'))

        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Created {created} lead(s), updated {updated}, skipped {skipped} '
            f'(duplicates/blank), created {tasks_created} task(s).'
        ))

    @staticmethod
    def _norm_status(s):
        return re.sub(r'[\s\-]+', '_', (s or '').strip().lower())

    @staticmethod
    def _resolve_user(name):
        name = name.strip()
        qs = User.objects
        user = qs.filter(username__iexact=name).first()
        if user:
            return user
        if '@' in name:
            user = qs.filter(email__iexact=name).first()
            if user:
                return user
        parts = name.split()
        if len(parts) >= 2:
            user = qs.filter(first_name__iexact=parts[0], last_name__iexact=' '.join(parts[1:])).first()
            if user:
                return user
        return qs.filter(first_name__iexact=name).first()
