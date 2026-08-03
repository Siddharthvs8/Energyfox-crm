"""Seed the number counters from the documents already issued.

The counter is new; the numbers are not. Without this the first document of
each series would be handed 001 again and collide with one already on paper.
"""
import re

from django.db import migrations

# REN2627-PI009  ->  ('REN2627-PI', 9)
PATTERN = re.compile(r'^(REN\d{4}-[A-Z]{2})(\d{3,})$')

SOURCES = [
    ('StockQuote', 'number'),
    ('StockDispatch', 'invoice_no'),
    ('StockPurchaseOrder', 'number'),
]


def seed(apps, schema_editor):
    Series = apps.get_model('inventory', 'DocumentNumberSeries')
    highest = {}
    for model_name, field in SOURCES:
        model = apps.get_model('inventory', model_name)
        for value in model.objects.values_list(field, flat=True):
            m = PATTERN.match(value or '')
            if not m:
                continue                       # legacy EF/… numbers and blanks
            key, seq = m.group(1), int(m.group(2))
            highest[key] = max(highest.get(key, 0), seq)

    for key, seq in highest.items():
        row, created = Series.objects.get_or_create(key=key, defaults={'last_seq': seq})
        if not created and row.last_seq < seq:
            row.last_seq = seq
            row.save(update_fields=['last_seq'])


def unseed(apps, schema_editor):
    apps.get_model('inventory', 'DocumentNumberSeries').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('inventory', '0013_documentnumberseries')]
    operations = [migrations.RunPython(seed, unseed)]
