"""Who a lead belongs to, in one place.

Several screens report figures over "my leads" — the dashboard, the converted
analytics, the leaderboard, My Performance. They used to each write their own
filter, and they disagreed: some counted only `assigned_to`, which reports
nothing for a BDE (a handed-over lead keeps the tele caller as its owner), and
none of them excluded deleted leads, so a lead in the Trash still counted
towards won revenue.

Both rules live here so a figure can never disagree with the rows behind it.
"""
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from datetime import timedelta

from django.utils import timezone

from .models import Lead, MaintenanceVisit


def own_leads_q(user):
    """The leads a plain user works: theirs to own, plus the two shared-ownership
    roles.

    Handing a lead to a BDE moves neither the tele caller nor the record of who
    is now on it — `assigned_to` stays with the tele caller and `bde` names the
    BDE — so scoping on the owner alone loses a BDE's entire book.
    """
    return Q(assigned_to=user) | Q(bde=user) | Q(tele_caller=user)


def live_leads():
    """Every lead that still counts.

    A lead in the Trash is gone as far as the customer is concerned, so counting
    its value as won revenue — or in any other figure — overstates the business.
    Restoring it from the Trash brings it back; this is a filter, not a write-off.
    """
    return Lead.objects.filter(is_trashed=False)



def maintenance_customers():
    """The customers Periodic Maintenance is about.

    A lead reaches the module by being pushed to liasoning, and leaves it the
    moment it is trashed — the Trash is out of every figure, here as everywhere.
    """
    return live_leads().filter(pushed_to_liasoning=True)


def maintenance_visits_due(on=None):
    """Visits calling for attention: the one definition the badge and the page
    both read.

    The sidebar badge used to count `MaintenanceVisit` rows outright, with no
    join back to a customer. A visit therefore went on being counted after its
    customer had been trashed or taken off liasoning, and the sidebar sat on a
    number the module itself could not show — a badge of 2 over a page reading
    "Nothing scheduled yet", which is exactly the sort of figure disagreeing
    with the rows behind it that this module exists to prevent.

    Counted from the day *before* they fall due, so the badge gives the officer
    a day's notice to arrange the trip.
    """
    day = (on or timezone.localdate()) + timedelta(days=MaintenanceVisit.REMINDER_LEAD_DAYS)
    return MaintenanceVisit.objects.filter(
        is_complete=False, due_date__lte=day,
        plan__lead__in=maintenance_customers(),
    )


def my_leads(user):
    """The live leads this user works — what their own figures are drawn from."""
    return live_leads().filter(own_leads_q(user)).distinct()

# ─── What counts as won ──────────────────────────────────────────────────────
# A deal is won when the money has landed — in accounts, with a payment (part or
# full) actually received. Not when someone marked the lead converted: that is a
# promise, and counting promises as wins overstates every figure built on them.
#
# One definition, in one place, because it is read by the dashboard, the
# Converted Leads board, the leaderboard, My Performance, the manager's employee
# report and the targets. Those numbers have to agree with each other and with
# the Closed Deals module, and they can only do that by asking the same question.
CLOSED_DEAL_FILTER = {
    'status': 'converted',
    'is_lost': False,
    'pushed_to_accounts': True,
    'payment_verification__amount_received__gt': 0,
}


def closed_deal_q(prefix=''):
    """The won-deal condition, ready to drop into a filter or an aggregate.

    `prefix` reaches the lead across a relation — `closed_deal_q('assigned_leads__')`
    for a Count over a user's leads, say.
    """
    return Q(**{f'{prefix}{field}': value for field, value in CLOSED_DEAL_FILTER.items()})


def closed_deals(qs=None):
    """The won deals in a queryset of leads (live ones by default)."""
    return (live_leads() if qs is None else qs).filter(**CLOSED_DEAL_FILTER)


# ─── What a won deal is worth ────────────────────────────────────────────────
# The agreed value, less the discount accounts gave. `Lead.value` is already net
# of the discount the BDE set on the site visit (it is price − discount), but
# accounts can give a further one when the money is taken, and that never
# reaches the lead. Summing `value` alone therefore reports revenue the business
# never charged for.
_MONEY = DecimalField(max_digits=16, decimal_places=2)


def net_value(prefix=''):
    """What a deal was *billed*: its worth after every discount.

    This is not revenue — see `received_value`. It is what the customer was
    asked for, which is the right figure for what is outstanding, for the value
    of an open pipeline, and for a deal-value column. Money still owed is in
    here; money in the bank is not.

    `prefix` reaches the lead across a relation — `net_value('bde_leads__')` for
    a Sum over a BDE's leads, say.
    """
    return ExpressionWrapper(
        Coalesce(F(f'{prefix}value'), Value(Decimal('0')))
        - Coalesce(F(f'{prefix}payment_verification__discount_value'), Value(Decimal('0'))),
        output_field=_MONEY,
    )


def received_value(prefix=''):
    """What was actually paid — the CRM's one definition of revenue.

    Revenue is money in, not money promised: a deal billed for a lakh with forty
    thousand received is forty thousand of revenue, and the rest is a debt. That
    is what every screen showing "revenue", "won value" or "converted revenue"
    reports, so a figure on one page cannot be a different kind of number from
    the same word on another.

    The billed figure has not gone away — it is `net_value`, and it is what
    outstanding is measured against.
    """
    return Coalesce(
        F(f'{prefix}payment_verification__amount_received'),
        Value(Decimal('0')),
        output_field=_MONEY,
    )


def closed_deal_revenue(qs=None):
    """Revenue from the won deals in a queryset — what was actually received."""
    return closed_deals(qs).aggregate(
        t=Coalesce(Sum(received_value()), Value(Decimal('0')), output_field=_MONEY))['t']
