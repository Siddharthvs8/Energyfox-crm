"""The customer's own view of their installation, and the link that opens it.

Documentation hands the customer a link once their paperwork clears; they open
it and watch the job move, the way a parcel is tracked. Two rules shape all of
this:

  * **No login.** Asking a homeowner to keep an account for one installation
    means nobody ever looks. The token in the URL is the credential, which is
    why it is 32 random bytes and why the payload below is so thin.
  * **Nothing internal leaves.** Stage names and the dates they were finished.
    No money, no staff names, no notes, no phone numbers, no lead id. Anyone
    holding the link sees exactly what the customer would be told on the phone.

The stages are read from the same flags the internal modules set, so the
customer's page cannot drift out of step with the CRM: a stage is done when the
department that owns it marked it done, not when someone remembered to update a
second copy of the truth.
"""
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Lead, TrackingLink


def _done(flag, when=None):
    return {'done': bool(flag), 'on': when.date().isoformat() if when else None}


def stages_for(lead):
    """The journey, in the order the customer experiences it.

    Each step is read off the department's own completion flag. A step is
    'current' when it is the first one not yet done — which is what gives the
    page its single highlighted row, as a parcel has one.
    """
    sv = getattr(lead, 'site_visit', None)
    s1 = getattr(lead, 'documentation_stage1', None)
    s2 = getattr(lead, 'documentation_stage2', None)
    pl = getattr(lead, 'purchase_logistics', None)
    pr = getattr(lead, 'project', None)

    steps = [
        {
            'key': 'documentation',
            'title': 'Documents verified',
            'blurb': 'We checked your paperwork and registered your application.',
            **_done(s1 and s1.is_complete, getattr(s1, 'completed_at', None)),
        },
        {
            'key': 'feasibility',
            'title': 'KSEB feasibility',
            'blurb': 'The board confirmed your connection can take the system.',
            'done': bool(sv and sv.kseb_feasibility_complete),
            'on': (sv.kseb_feasibility_date.isoformat()
                   if sv and sv.kseb_feasibility_date else None),
        },
        {
            'key': 'approvals',
            'title': 'Approvals cleared',
            'blurb': 'Sanction received, and your installation is scheduled.',
            **_done(s2 and s2.is_complete, getattr(s2, 'completed_at', None)),
        },
        {
            'key': 'materials',
            'title': 'Materials dispatched',
            'blurb': 'Panels and inverter are on their way to your site.',
            **_done(pl and pl.is_complete, getattr(pl, 'completed_at', None)),
        },
        {
            'key': 'installation',
            'title': 'Installation complete',
            'blurb': 'Your system is installed and generating.',
            **_done(pr and pr.is_complete, getattr(pr, 'completed_at', None)),
        },
    ]

    # The journey only runs forwards. Departments mark their own stage complete
    # and they do not always do it in order — a job can be installed while the
    # approval record is still open — which left the customer looking at
    # "installed" above "approval in progress" and a tracker that appears
    # broken. Anything before a finished stage is therefore shown as reached.
    #
    # This is not a fiction: the work genuinely cannot be installed before it is
    # approved, so a later completion is proof the earlier step happened and the
    # record is merely lagging. The earlier step keeps whatever date it has and
    # shows none if it has not been stamped, rather than borrowing one.
    reached = False
    for step in reversed(steps):
        if step['done']:
            reached = True
        elif reached:
            step['done'] = True
            step['inferred'] = True

    # Exactly one step is 'current': the first that is not done. When every step
    # is done there is no current one, and the page shows the job as finished.
    current = next((s for s in steps if not s['done']), None)
    for step in steps:
        step['current'] = step is current
        step.setdefault('inferred', False)
    return steps


def tracking_payload(link):
    """What the public page is allowed to know."""
    lead = link.lead
    steps = stages_for(lead)
    done = [s for s in steps if s['done']]
    return {
        # A first name only. Enough for the customer to see the page is theirs,
        # not enough to be a customer list if a link is forwarded.
        'customer': (lead.first_name or '').strip() or 'Customer',
        'stages': steps,
        'steps_done': len(done),
        'steps_total': len(steps),
        'complete': len(done) == len(steps),
        'started_on': lead.created_at.date().isoformat() if lead.created_at else None,
        'last_update': max((s['on'] for s in done if s['on']), default=None),
    }


class TrackingLinkView(APIView):
    """The customer's tracking page, open to anyone holding the link.

    Deliberately unauthenticated — see the module docstring. The token is the
    credential, so the only checks are that it exists, has not been revoked, and
    has not expired.

    A wrong token and an expired one answer differently on purpose: "expired" is
    something the customer can act on by asking for a new link, whereas a bare
    404 for both would leave them thinking the company had lost their job.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, token):
        link = (TrackingLink.objects
                .select_related('lead', 'lead__site_visit', 'lead__documentation_stage1',
                                'lead__documentation_stage2', 'lead__purchase_logistics',
                                'lead__project')
                .filter(token=token).first())

        if link is None or link.revoked or link.lead.is_trashed:
            return Response({'error': 'not_found',
                             'message': 'This tracking link is not valid.'},
                            status=status.HTTP_404_NOT_FOUND)

        if not link.is_live:
            return Response({'error': 'expired',
                             'message': 'This tracking link has expired. '
                                        'Please ask us for a new one.'},
                            status=status.HTTP_410_GONE)

        # Counted with update() rather than save(): a customer refreshing their
        # page should never race the office editing the same row.
        TrackingLink.objects.filter(pk=link.pk).update(
            view_count=link.view_count + 1, last_viewed_at=timezone.now())

        return Response(tracking_payload(link))
