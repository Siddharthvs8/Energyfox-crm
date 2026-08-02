"""Who a lead belongs to, in one place.

Several screens report figures over "my leads" — the dashboard, the converted
analytics, the leaderboard, My Performance. They used to each write their own
filter, and they disagreed: some counted only `assigned_to`, which reports
nothing for a BDE (a handed-over lead keeps the tele caller as its owner), and
none of them excluded deleted leads, so a lead in the Trash still counted
towards won revenue.

Both rules live here so a figure can never disagree with the rows behind it.
"""
from django.db.models import Q

from .models import Lead


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


def my_leads(user):
    """The live leads this user works — what their own figures are drawn from."""
    return live_leads().filter(own_leads_q(user)).distinct()
