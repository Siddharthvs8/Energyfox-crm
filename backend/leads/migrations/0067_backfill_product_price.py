from django.db import migrations


def backfill(apps, schema_editor):
    """Seed product_price from the deal value already on the lead.

    The deal value is derived from price − discount from now on, so a site visit
    left at a price of 0 would recompute an existing deal down to nothing the
    first time a BDE saved it. Carrying the figure across means every deal on the
    books keeps the value it already had, with no discount recorded against it —
    which is exactly what was true before there was a discount field.
    """
    SiteVisit = apps.get_model('leads', 'SiteVisit')
    updates = []
    for sv in SiteVisit.objects.select_related('lead').iterator():
        value = sv.lead.value or 0
        if value and not sv.product_price:
            sv.product_price = value
            updates.append(sv)
    if updates:
        SiteVisit.objects.bulk_update(updates, ['product_price'], batch_size=500)


def unbackfill(apps, schema_editor):
    """Nothing to undo: the deal value it was copied from is still on the lead,
    and the columns themselves go with the previous migration."""


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0066_sitevisit_discount_sitevisit_product_price'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
