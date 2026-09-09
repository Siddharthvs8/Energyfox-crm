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

from .models import Lead, LiasoningService, TrackingLink


def _done(flag, when=None):
    # Read in the company's own timezone, not UTC. Everything here is stamped as
    # an aware UTC datetime, so a sign-off at 2am IST falls on the previous UTC
    # day — and the customer would be shown a date one behind the one they were
    # given on the phone.
    return {'done': bool(flag),
            'on': timezone.localtime(when).date().isoformat() if when else None}


def stages_for(lead):
    """The journey, in the order the customer experiences it.

    Each step is read off the department's own completion flag. A step is
    'current' when it is the first one not yet done — which is what gives the
    page its single highlighted row, as a parcel has one.

    Two of the steps are conditional, because showing them to everyone would be
    telling most customers about something that will never happen to them:

      * **Loan sanctioned** appears only when the site visit recorded a loan.
      * **Subsidy claimed** appears only once the discom has approved, which is
        the moment a subsidy stops being a maybe. A customer the discom turned
        down never sees it, and nobody is shown a subsidy row that later has to
        disappear.
    """
    sv = getattr(lead, 'site_visit', None)
    s1 = getattr(lead, 'documentation_stage1', None)
    s2 = getattr(lead, 'documentation_stage2', None)
    pl = getattr(lead, 'purchase_logistics', None)
    pr = getattr(lead, 'project', None)
    wr = getattr(lead, 'warranty', None)
    lia = getattr(lead, 'liasoning_service', None)

    # The RF image is the registration receipt the liasoning officer photographs
    # at the board's counter, so the picture itself is the completion flag —
    # there is no separate tick to fall out of step with it. Its upload time is
    # the date the customer is shown.
    rf = (lia.documents.filter(doc_type=LiasoningService.RF_IMAGE)
          .order_by('uploaded_at', 'id').first()) if lia else None

    # ── The spine: one thing after another, in this order, always ──
    spine = [
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
    ]

    if sv and sv.loan == 'yes':
        spine.append({
            'key': 'loan',
            'title': 'Loan sanctioned',
            'blurb': 'Your bank approved the finance for this installation.',
            **_done(s1 and s1.loan_sanctioned, getattr(s1, 'loan_sanctioned_at', None)),
        })

    spine += [
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

    # ── After the installation: jobs that run side by side ──
    # Registration, commissioning, the board's approval, the subsidy claim and
    # the warranty are independent of each other: the warranty can be issued
    # before the subsidy is filed or long after it, so none of them is evidence
    # of another. They are kept out of the spine for exactly that reason — see
    # the forwards-only rule below.
    after = [{
        'key': 'kseb_registration',
        'title': 'KSEB registration and completion',
        # Neutral on purpose: a pending row must not tell a customer their
        # system is registered with the board when it is not.
        'blurb': 'We register your installed system with KSEB and file your '
                 'completion documents.',
        **_done(rf, getattr(rf, 'uploaded_at', None)),
    }, {
        'key': 'commissioning',
        'title': 'Commissioning',
        # Written as the finished state, the way 'Installation complete' above
        # is: it is the moment the customer has been waiting for, and the row is
        # visibly greyed until it happens. The filing that gets there is
        # described on the registration row above, so it is not repeated here.
        'blurb': 'Your plant is now on and generating.',
        # The officer's Completed tick. Signing the record off is what that tick
        # does once both photos are in, and it is the half that carries a date;
        # the bare flag is read as well so a row ticked before the photo rule
        # existed still shows the customer what the office already believes.
        **_done(lia and (lia.is_complete or lia.annexure3_completed),
                getattr(lia, 'completed_at', None)),
    }, {
        'key': 'discom_approval',
        'title': 'KSEB approval',
        # Neutral on purpose: this row is pending for a customer whose approval
        # has not come in, and it must not read as though it had.
        'blurb': 'The board approves your completed installation.',
        # Only 'yes' counts. 'no' is a refusal, not a step still to come, and
        # 'pending' is the default every record starts on.
        **_done(s2 and s2.discom_approval == 'yes',
                getattr(s2, 'discom_approval_at', None)),
    }]
    after.append({
        'key': 'warranty',
        'title': 'Warranty issued',
        'blurb': 'Your warranty certificate has been issued and sent to you.',
        **_done(wr and wr.is_complete, getattr(wr, 'completed_at', None)),
    })
    # The claim goes in last, after the warranty is issued, so it reads to the
    # customer in the order the office works. Ordering only: these steps are
    # still independent of each other and neither infers the other.
    if s2 and s2.discom_approval == 'yes':
        after.append({
            'key': 'subsidy',
            'title': 'Subsidy claimed',
            # Written so it reads true whether the step is done or still to
            # come — a pending row saying the claim "has been filed" is a
            # statement about the customer's money that is not yet true. It also
            # never says the subsidy has been *paid*: claiming and receiving are
            # months apart, and this page must not blur them.
            'blurb': 'We claim your national subsidy from MNRE on your behalf.',
            **_done(s2.subsidy_requested, s2.subsidy_requested_at),
        })

    # The journey only runs forwards — but only along the spine. Departments
    # mark their own stage complete and they do not always do it in order: a job
    # can be installed while the approval record is still open, which left the
    # customer looking at "installed" above "in progress" and a tracker that
    # appears broken. Anything before a finished spine step is shown as reached.
    #
    # This is not a fiction: the work genuinely cannot be installed before it is
    # approved, so a later completion is proof the earlier step happened and the
    # record is merely lagging. The earlier step keeps whatever date it has and
    # shows none if it has not been stamped, rather than borrowing one.
    #
    # The rule stops at the installation. The subsidy and the warranty are
    # parallel tasks with no order between them, so an issued warranty is no
    # evidence at all that the subsidy was claimed — inferring it would tell a
    # customer their claim was filed when it was not.
    #
    # KSEB registration is kept out of the spine for the same reason. A
    # liasoning record can be opened from the discom sync before the project is
    # signed off, so an RF image is not proof the installation is finished, and
    # inferring it would tell a customer their system is up when it is not.
    reached = False
    for step in reversed(spine):
        if step['done']:
            reached = True
        elif reached:
            step['done'] = True
            step['inferred'] = True

    steps = spine + after

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
                                'lead__project', 'lead__warranty',
                                'lead__liasoning_service')
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
