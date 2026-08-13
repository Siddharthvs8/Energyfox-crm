"""Finding and merging leads that are the same customer twice.

The same person reaches the CRM more than once — they fill the Meta form again,
they turn up in two spreadsheets, a tele caller files them a second time. Left
alone they become two histories of one customer, and whoever calls second does
not know the first call happened.

Two leads are the same customer when they share a phone number or an email
address. Phone matching works on the last ten digits, so `+919380077570` and
`9380077570` are one number rather than two — that difference is the single
biggest source of duplicates the import route produces.

Merging keeps the lead you choose and sends the rest to Trash, moving their
history across first so nothing said to the customer is lost. It refuses to
discard a lead carrying real work — a site visit, paperwork, money, a project —
because that is a record of something that actually happened and cannot be
folded into another row automatically.
"""
import re
from collections import OrderedDict

from django.db import transaction
from django.utils import timezone

from .models import ActivityLog, Lead
from .scopes import live_leads

_NON_DIGITS = re.compile(r'\D+')

# Indian mobile numbers are ten digits; anything in front is a country code or
# dialling prefix that says nothing about who the customer is.
LOCAL_DIGITS = 10


def normalise_phone(raw):
    """The comparable part of a phone number, or '' when there isn't one.

    Everything but the digits goes, then the last ten are kept. Shorter numbers
    are returned as they are — a landline or a half-entered number still matches
    another copy of itself, it just cannot be compared against a mobile.
    """
    digits = _NON_DIGITS.sub('', str(raw or ''))
    if not digits:
        return ''
    return digits[-LOCAL_DIGITS:] if len(digits) >= LOCAL_DIGITS else digits


def normalise_email(raw):
    return str(raw or '').strip().lower()


# History that belongs to the customer, so it follows them to the kept lead.
# Each is a plain foreign key: reassigning it moves the record, it does not copy.
HISTORY_RELATIONS = (
    ('activity_logs', 'lead'),
    ('note_entries', 'lead'),
    ('attachments', 'lead'),
    ('shared_documents', 'lead'),
    ('tasks', 'lead'),
    ('calls', 'lead'),
    ('whatsapp_messages', 'lead'),
    ('email_messages', 'lead'),
)

# Work that cannot be merged. Each is a stage record or a money record: one lead
# can only have one of them, and combining two would mean choosing which set of
# real events to throw away. A lead carrying any of these can be *kept*, never
# discarded.
BLOCKING_RELATIONS = OrderedDict((
    ('site_visit', 'a site visit'),
    ('documentation_stage1', 'documentation'),
    ('payment_verification', 'a payment'),
    ('purchase_logistics', 'purchase & logistics'),
    ('project', 'a project'),
    ('documentation_stage2', 'stage 2 documentation'),
    ('warranty', 'a warranty'),
    ('liasoning_service', 'liasoning'),
    ('periodic_maintenance', 'a maintenance schedule'),
))

BLOCKING_SETS = OrderedDict((
    ('balance_payments', 'balance payments'),
    ('receipt_vouchers', 'receipts'),
    ('quotes', 'quotes'),
    ('sales_orders', 'sales orders'),
))

# Fields worth carrying over when the kept lead has nothing in them. Only blanks
# are filled: what is already on the kept lead is what the user chose to keep.
FILLABLE_FIELDS = (
    'email', 'phone', 'last_name', 'company', 'district', 'installation_location',
    'source', 'value', 'product', 'assigned_to', 'bde', 'tele_caller', 'campaign',
)


def blockers_for(lead):
    """Why this lead cannot be merged away, in words a user can act on."""
    found = []
    for relation, label in BLOCKING_RELATIONS.items():
        if hasattr(lead, relation):
            found.append(label)
    for relation, label in BLOCKING_SETS.items():
        manager = getattr(lead, relation, None)
        if manager is not None and manager.exists():
            found.append(label)
    if lead.status == 'converted':
        found.append('a converted deal')
    return found


def _display(lead):
    name = ' '.join(part for part in (lead.first_name, lead.last_name) if part)
    return name.strip() or lead.phone or lead.email or f'Lead #{lead.pk}'


def lead_row(lead):
    owner = lead.assigned_to
    return {
        'id': lead.pk,
        'name': _display(lead),
        'first_name': lead.first_name or '',
        'last_name': lead.last_name or '',
        'phone': lead.phone or '',
        'email': lead.email or '',
        'status': lead.status,
        'source': lead.source or '',
        'district': lead.district or '',
        'created_at': lead.created_at.isoformat() if lead.created_at else None,
        'owner': (f'{owner.first_name} {owner.last_name}'.strip() or owner.username) if owner else None,
        'blockers': blockers_for(lead),
    }


def find_duplicate_groups(queryset=None):
    """Every set of leads that share a phone or an email.

    Phone groups are built first and email groups only reported when they turn
    up a pairing the phone pass missed — otherwise the common case, where two
    copies of one customer share both, would be listed twice and merging one
    would leave a stale second group on screen.
    """
    leads = list(
        (live_leads() if queryset is None else queryset)
        .select_related('assigned_to')
        .order_by('created_at', 'pk')
    )

    by_phone, by_email = OrderedDict(), OrderedDict()
    for lead in leads:
        phone = normalise_phone(lead.phone)
        if phone:
            by_phone.setdefault(phone, []).append(lead)
        email = normalise_email(lead.email)
        if email:
            by_email.setdefault(email, []).append(lead)

    groups = []
    seen_pairs = set()

    def pairs_of(members):
        ids = sorted(m.pk for m in members)
        return {(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]}

    for key, members in by_phone.items():
        if len(members) < 2:
            continue
        seen_pairs |= pairs_of(members)
        groups.append({'match': 'phone', 'key': key, 'leads': members})

    for key, members in by_email.items():
        if len(members) < 2:
            continue
        # Nothing new if every pairing here is already covered by a phone group.
        if pairs_of(members) <= seen_pairs:
            continue
        seen_pairs |= pairs_of(members)
        groups.append({'match': 'email', 'key': key, 'leads': members})

    # Newest activity first: a duplicate created today is the one someone is
    # about to call twice.
    groups.sort(key=lambda g: max(m.created_at for m in g['leads']), reverse=True)
    return groups


def serialise_groups(groups):
    return [{
        'match': g['match'],
        'key': g['key'],
        'count': len(g['leads']),
        # The oldest is offered as the one to keep: it holds the history, and
        # the later copy is the accident.
        'suggested_keep': g['leads'][0].pk,
        'leads': [lead_row(lead) for lead in g['leads']],
    } for g in groups]


class MergeRefused(Exception):
    """A merge that would destroy real work, with the reason to show."""


@transaction.atomic
def merge_leads(keep, discard, actor=None):
    """Fold `discard` into `keep`, and send the discarded leads to Trash.

    Blanks on the kept lead are filled from the discarded ones, oldest first,
    and their history is moved across. The discarded rows are trashed rather
    than destroyed, so a merge made in error can be undone from the Trash.
    """
    discard = [lead for lead in discard if lead.pk != keep.pk]
    if not discard:
        raise MergeRefused('Choose at least one other lead to merge in.')

    for lead in discard:
        blockers = blockers_for(lead)
        if blockers:
            raise MergeRefused(
                f'{_display(lead)} has {", ".join(blockers)}, so it cannot be merged away. '
                f'Keep that one instead, or sort the two out by hand.')

    filled = []
    for lead in discard:
        for field in FILLABLE_FIELDS:
            if getattr(keep, f'{field}_id', None) is not None or getattr(keep, field, None):
                continue                       # the kept lead already has one
            value = getattr(lead, f'{field}_id', None) or getattr(lead, field, None)
            if value:
                setattr(keep, f'{field}_id' if hasattr(lead, f'{field}_id') else field, value)
                filled.append(field)

    # Notes are appended rather than filled: two notes are two things the
    # customer said, and dropping either loses the call that produced it.
    extra_notes = [lead.notes.strip() for lead in discard if (lead.notes or '').strip()]
    if extra_notes:
        keep.notes = '\n\n'.join([(keep.notes or '').strip(), *extra_notes]).strip()

    keep.save()

    moved = 0
    for relation, field in HISTORY_RELATIONS:
        for lead in discard:
            manager = getattr(lead, relation, None)
            if manager is not None:
                moved += manager.update(**{field: keep})

    now = timezone.now()
    for lead in discard:
        lead.is_trashed = True
        if hasattr(lead, 'trashed_at'):
            lead.trashed_at = now
        lead.save(update_fields=[f for f in ('is_trashed', 'trashed_at')
                                 if hasattr(lead, f)])

    ActivityLog.objects.create(
        activity_type='note_added',
        description=(f"Merged {len(discard)} duplicate lead(s) into this one: "
                     f"{', '.join(_display(l) for l in discard)}."),
        actor=actor if (actor and actor.is_authenticated) else None,
        lead=keep,
        extra={'auto_generated': True, 'merged_ids': [l.pk for l in discard],
               'fields_filled': sorted(set(filled)), 'records_moved': moved},
    )

    return {'kept': keep.pk, 'merged': [l.pk for l in discard],
            'fields_filled': sorted(set(filled)), 'records_moved': moved}


def existing_duplicate_of(phone='', email='', exclude_pk=None):
    """A live lead that already holds this phone or email, if there is one.

    What `create` and the importer check against. Phone is compared on its last
    ten digits, email case-insensitively, so the copy that arrives formatted
    differently is still recognised as the same customer.
    """
    phone_key, email_key = normalise_phone(phone), normalise_email(email)
    if not phone_key and not email_key:
        return None

    candidates = live_leads()
    if exclude_pk:
        candidates = candidates.exclude(pk=exclude_pk)

    if email_key:
        hit = candidates.filter(email__iexact=email_key).first()
        if hit is not None:
            return hit

    if phone_key:
        # The stored value may carry a country code or spacing, so the digits
        # have to be compared rather than the string as typed. Narrowing on the
        # last four first keeps this off a full scan of the lead book — they are
        # contiguous in every way a number gets written down, whereas the whole
        # number is not once it is grouped with spaces.
        candidates = candidates.exclude(phone='')
        if len(phone_key) >= 4:
            candidates = candidates.filter(phone__contains=phone_key[-4:])
        for lead in candidates.only('id', 'phone', 'first_name', 'last_name', 'email'):
            if normalise_phone(lead.phone) == phone_key:
                return lead
    return None
