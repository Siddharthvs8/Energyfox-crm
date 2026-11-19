"""A quotation's life, on its customer's Activity Timeline.

Raising a quotation and changing one are the moments a price is put in front of
a customer, and the people who pick the file up later — accounts, the project
team, a manager asking why the figure moved — read the customer's timeline, not
the quotation. So both are written there, under whoever did it, and an edit says
what it changed: "Discount: ₹0 → ₹15,000" answers the question that a bare
"edited" only raises.

Called from QuotationViewSet, which is how a person writes a quotation. The
saves the system makes by itself — numbering it, marking it sent when it goes
out, stamping it an order when the money arrives — are not edits and are not
recorded here; sending has its own entry (see deliver_document).
"""
from decimal import Decimal

from leads.models import ActivityLog
from rewards.models import rupees

from .models import Quotation


def _money(value):
    return f'₹{rupees(value or 0)}'


def _date(value):
    return value.strftime('%d %b %Y') if value else '—'


def _percent(value):
    return f'{Decimal(value or 0).normalize():f}%'


def _text(value, limit=80):
    """One line, cut short: an entry is a sentence, not a copy of the field."""
    text = ' '.join(str(value or '').split())
    if not text:
        return '—'
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def _customer(lead):
    if lead is None:
        return 'No customer'
    name = f'{lead.first_name or ""} {lead.last_name or ""}'.strip()
    return name or lead.phone or f'Lead #{lead.pk}'


def _items(n):
    return f'{n} item' if n == 1 else f'{n} items'


def _actor(user):
    return user if user is not None and user.is_authenticated else None


def snapshot(quotation):
    """The quotation as stored right now, field by field in the form's order.

    Each field is (value to compare, what to print). Read afresh rather than off
    the instance being saved: the viewset prefetches the specification and the
    costs, and that cache still holds the old lists after the serializer has
    rewritten them.
    """
    q = Quotation.objects.select_related('lead', 'project').get(pk=quotation.pk)
    spec = [(l.item_name, l.brand, l.quantity)
            for l in q.spec_lines.order_by('position', 'id')]
    costs = [(c.remark, c.amount) for c in q.costs.order_by('position', 'id')]
    extras = sum((amount or Decimal('0') for _, amount in costs), Decimal('0'))
    return {
        'quotation': q,
        'fields': {
            'Customer': (q.lead_id, _customer(q.lead)),
            'Status': (q.status, q.get_status_display()),
            'Quotation date': (q.quotation_date, _date(q.quotation_date)),
            'Valid until': (q.expiry_date, _date(q.expiry_date)),
            'Project': (q.project_id, q.project.name if q.project else 'No project'),
            'Variant': (q.price_variant, q.get_price_variant_display()),
            # A list is compared whole. Its count is the part worth printing;
            # when the count stands, the entry just says the list was edited.
            'Specifications': (spec, _items(len(spec))),
            'Package price': (q.package_amount, _money(q.package_amount)),
            'Subsidy': (q.subsidy_amount, _money(q.subsidy_amount)),
            'Tax': (q.tax_percent, _percent(q.tax_percent)),
            'Price includes tax': (q.price_includes_tax, 'Yes' if q.price_includes_tax else 'No'),
            'Additional costs': (costs, _money(extras)),
            'Discount': (q.discount_amount, _money(q.discount_amount)),
            'Discount reason': (q.discount_remark.strip(), _text(q.discount_remark)),
            'Site': (q.site.strip(), _text(q.site)),
            # Said to have changed, never quoted: notes run to paragraphs.
            'Notes': (q.notes.strip(), None),
            # Last, because it is what the changes above came to.
            'Total': (q.grand_total, _money(q.grand_total)),
        },
    }


def changes_between(before, after):
    """What a save changed, as [{field, from, to}]; from/to are None where the
    entry only says the field was edited."""
    out = []
    for field, (old, old_shown) in before['fields'].items():
        new, new_shown = after['fields'][field]
        if old == new:
            continue
        if old_shown is None or old_shown == new_shown:
            out.append({'field': field, 'from': None, 'to': None})
        else:
            out.append({'field': field, 'from': old_shown, 'to': new_shown})
    return out


def _phrase(change):
    if change['from'] is None:
        return f"{change['field']} edited"
    return f"{change['field']}: {change['from']} → {change['to']}"


def record_created(quotation, actor):
    """Put a newly raised quotation on its customer's timeline.

    A quotation raised with no customer has no timeline to go on; it reaches one
    when it is given a customer, as an edit.
    """
    q = Quotation.objects.select_related('lead', 'project').get(pk=quotation.pk)
    if q.lead_id is None:
        return None
    parts = []
    if q.project:
        parts.append(f'{q.project.name} ({q.get_price_variant_display()})')
    total = _money(q.grand_total)
    if q.discount_amount:
        reason = q.discount_remark.strip()
        total += (f' after a {_money(q.discount_amount)} discount'
                  + (f' ({_text(reason)})' if reason else ''))
    parts.append(total)
    if q.status != 'draft':
        parts.append(f'status {q.get_status_display()}')
    return ActivityLog.objects.create(
        activity_type='quotation_created', lead_id=q.lead_id, actor=_actor(actor),
        description=f'Quotation {q.number} created — {", ".join(parts)}.',
        extra={'quotation': q.pk, 'number': q.number, 'total': str(q.grand_total)},
    )


def record_edited(before, quotation, actor):
    """Put an edit on the timeline, saying what it changed.

    A save that changed nothing is not an edit and leaves no entry. A quotation
    moved to another customer is written on both timelines: the one it left
    would otherwise show it raised and then never mention it again.
    """
    after = snapshot(quotation)
    changes = changes_between(before, after)
    if not changes:
        return []
    q = after['quotation']
    description = f'Quotation {q.number} edited — {"; ".join(map(_phrase, changes))}.'
    leads = []
    for lead_id in (q.lead_id, before['quotation'].lead_id):
        if lead_id and lead_id not in leads:
            leads.append(lead_id)
    return [ActivityLog.objects.create(
        activity_type='quotation_edited', lead_id=lead_id, actor=_actor(actor),
        description=description,
        extra={'quotation': q.pk, 'number': q.number, 'changes': changes},
    ) for lead_id in leads]
