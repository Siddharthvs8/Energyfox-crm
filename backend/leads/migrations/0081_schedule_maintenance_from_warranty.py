"""Put customers whose warranty is already issued on periodic maintenance,
counted from the day it was: the day its certificate was generated, or for a
warranty completed without one, the day it was completed (Warranty.issued_on).

From now on generating the certificate schedules the customer by itself
(LeadViewSet.warranty_add_document), and so does completing a warranty that has
none. This catches up the ones issued before that rule, who would otherwise sit
under "not yet scheduled" waiting for a warranty they already have. Anyone
already on the schedule keeps it.

No automation is fired for them: a rule that messages the customer about their
schedule should not go out to every one of them at once on the day this runs.
"""
import calendar
from datetime import date

from django.db import migrations
from django.utils import timezone

# Copied rather than imported, so this migration keeps doing what it did when
# the code it mirrors changes: Warranty.CERTIFICATE_PREFIX,
# PeriodicMaintenance.VISIT_COUNT / GAP_MONTHS and LeadViewSet._add_months.
PREFIX = 'Warranty_Certificate'
VISIT_COUNT = 10
GAP_MONTHS = 6


def add_months(d, months):
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def schedule_from_warranty(apps, schema_editor):
    Lead = apps.get_model('leads', 'Lead')
    Warranty = apps.get_model('leads', 'Warranty')
    WarrantyDocument = apps.get_model('leads', 'WarrantyDocument')
    PeriodicMaintenance = apps.get_model('leads', 'PeriodicMaintenance')
    MaintenanceVisit = apps.get_model('leads', 'MaintenanceVisit')
    ActivityLog = apps.get_model('leads', 'ActivityLog')

    waiting = Lead.objects.filter(is_trashed=False, pushed_to_liasoning=True,
                                  periodic_maintenance__isnull=True)
    issued = {}
    for lead_id, name, at in (WarrantyDocument.objects
                              .filter(warranty__lead__in=waiting, doc_type='warranty')
                              .order_by('uploaded_at', 'id')
                              .values_list('warranty__lead_id', 'file', 'uploaded_at')):
        if (name or '').rsplit('/', 1)[-1].startswith(PREFIX):
            issued.setdefault(lead_id, at)
    # Only where there is no certificate: a completed warranty is locked, so
    # one completed without a certificate will never be given one.
    for lead_id, at in (Warranty.objects
                        .filter(lead__in=waiting, is_complete=True, completed_at__isnull=False)
                        .values_list('lead_id', 'completed_at')):
        issued.setdefault(lead_id, at)

    for lead_id, at in issued.items():
        # The company's day, not UTC's: a certificate made at 1 am IST was
        # made that day.
        start = timezone.localtime(at).date()
        plan = PeriodicMaintenance.objects.create(lead_id=lead_id, start_date=start)
        MaintenanceVisit.objects.bulk_create([
            MaintenanceVisit(plan=plan, sequence=i, due_date=add_months(start, GAP_MONTHS * i))
            for i in range(1, VISIT_COUNT + 1)])
        ActivityLog.objects.create(
            activity_type='note_added', lead_id=lead_id,
            description=(f"Scheduled for periodic maintenance from the warranty date, "
                         f"{start.strftime('%d/%m/%Y')}: {VISIT_COUNT} visits every "
                         f"{GAP_MONTHS} months."),
            extra={'auto_generated': True})


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0080_lead_bde_assigned_at'),
    ]

    operations = [
        migrations.RunPython(schedule_from_warranty, migrations.RunPython.noop),
    ]
