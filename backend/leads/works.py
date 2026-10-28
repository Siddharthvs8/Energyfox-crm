"""Works — every customer between the site visit and a finished project.

Three desks in the middle of the pipeline each own one stage of it: the
documentation manager owns Documentation Stage 1, the accounts manager Accounts,
the project manager Project. Works shows them the whole pipeline, split at their
own stage:

  * upcoming  — the stages before theirs: work that is on its way to them.
  * completed — the stages after theirs: work that has passed them.

Work sitting at their own stage is in neither list. It is already in their own
module, and the page sends them there rather than listing it twice.

The stages are the Leads page's own — Lead.pipeline_stage and the `stage`
filter in LeadViewSet.get_queryset — with Project split in two, in progress and
complete, because a finished installation is where this pipeline ends. If those
change, these have to follow, or a customer would sit in one stage here and in
another on the Leads page.

A work is a live lead that is still going ahead. A deal marked lost and a lead
marked not interested are left out at every stage, since neither is coming to
anyone. Archived leads stay in, as they do in every module queue: archiving
clears a lead out of the Leads list, not out of the pipeline, and most of the
archive is finished projects — exactly what "completed" is asked to show.
"""
from typing import NamedTuple

from django.db.models import Count, F, Q, Value
from django.db.models.functions import Coalesce, Concat
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .scopes import live_leads


class Stage(NamedTuple):
    key: str
    label: str
    blurb: str
    where: Q             # the leads sitting in this stage now
    since: str           # the field dated by their arrival in it
    handler: str         # the Lead field naming who has them now
    handler_label: str


_NOT_PUSHED = Q(pushed_to_documentation=False, pushed_to_accounts=False,
                pushed_to_purchase=False, pushed_to_project=False)
_AT_BDE = _NOT_PUSHED & Q(bde__isnull=False)

# In pipeline order. Each stage excludes every further one, so a customer is in
# exactly one of them.
STAGES = [
    # isnull=True across the reverse one-to-one is a LEFT JOIN, so a lead with
    # no site visit record yet is still at the site visit.
    Stage('site_visit', 'Site Visit', 'With the BDE. The PO is not signed yet.',
          _AT_BDE & Q(site_visit__po_signed_date__isnull=True),
          'bde_assigned_at', 'bde', 'BDE'),
    Stage('po_signed', 'PO Signed', 'PO signed, on its way to documentation.',
          _AT_BDE & Q(site_visit__po_signed_date__isnull=False),
          'site_visit__po_signed_date', 'bde', 'BDE'),
    Stage('documentation', 'Documentation S1', 'Paperwork with the documentation team.',
          Q(pushed_to_documentation=True, pushed_to_accounts=False,
            pushed_to_purchase=False, pushed_to_project=False),
          'pushed_to_documentation_at', 'documentation_staff', 'Documentation'),
    Stage('accounts', 'Accounts', 'Payment being verified by accounts.',
          Q(pushed_to_accounts=True, pushed_to_purchase=False, pushed_to_project=False),
          'pushed_to_accounts_at', 'accounts_staff', 'Accounts'),
    Stage('purchase', 'Purchase & Logistics', 'Materials being bought and dispatched.',
          Q(pushed_to_purchase=True, pushed_to_project=False),
          'pushed_to_purchase_at', 'purchase_staff', 'Purchase'),
    Stage('project', 'Project', 'Installation under way.',
          Q(pushed_to_project=True) & (Q(project__isnull=True) | Q(project__is_complete=False)),
          'pushed_to_project_at', 'project_manager', 'Project manager'),
    Stage('completed', 'Project Completed', 'Installation finished.',
          Q(pushed_to_project=True, project__is_complete=True),
          'project__completed_at', 'project_manager', 'Project manager'),
]
STAGE_INDEX = {s.key: i for i, s in enumerate(STAGES)}

# Each desk, the stage it owns, and the module where that stage's work is
# done. The sidebar offers Works to exactly these roles (`worksFeature` in
# layout.tsx); if this changes, change that too.
DESKS = {
    'documentation_manager': ('documentation', '/documentation'),
    'accounts_manager': ('accounts', '/accounts'),
    'project_manager': ('project', '/project'),
}


def desk_of(user):
    """(stage, module) for the user's desk, or None when Works is not for them.

    Only the three desks. Works is drawn around the viewer's own stage, so a role
    without one — an admin, the spectator, a custom user type — has no "before"
    or "after" to be shown, and is not offered the module.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    return DESKS.get(getattr(user, 'role', ''))


def _day(value):
    """A stage date as the company reads it.

    Timestamps are read in the site's time zone, not UTC: a push at 11 pm IST
    happened that day, not the next one. The PO date is already a plain date.
    """
    if not value:
        return None
    if hasattr(value, 'hour'):
        value = timezone.localtime(value).date()
    return value.isoformat()


def _name(user):
    if not user:
        return None
    full = ' '.join(p.strip() for p in (user.first_name or '', user.last_name or '') if p.strip())
    return full or user.username


def _work(lead, stage):
    """One customer as Works lists it, with the road they took to get here."""
    sv = getattr(lead, 'site_visit', None)
    pr = getattr(lead, 'project', None)
    reached = {
        'site_visit': lead.bde_assigned_at,
        'po_signed': sv.po_signed_date if sv else None,
        'documentation': lead.pushed_to_documentation_at,
        'accounts': lead.pushed_to_accounts_at,
        'purchase': lead.pushed_to_purchase_at,
        'project': lead.pushed_to_project_at,
        'completed': pr.completed_at if pr and pr.is_complete else None,
    }
    people = {
        'site_visit': lead.bde,
        'po_signed': lead.bde,
        'documentation': lead.documentation_staff,
        'accounts': lead.accounts_staff,
        'purchase': lead.purchase_staff,
        'project': lead.project_manager,
        'completed': (pr.completed_by if pr else None) or lead.project_manager,
    }
    return {
        'id': lead.id,
        # Joined from the parts that exist: most Meta leads have no last name,
        # and formatting the pair straight would list "Asha None".
        'name': ' '.join(p.strip() for p in (lead.first_name or '', lead.last_name or '') if p.strip()),
        'phone': lead.phone,
        'place': lead.company,
        'district': lead.district,
        'product': lead.product.name if lead.product else None,
        'value': str(lead.value or 0),
        'bde_name': _name(lead.bde),
        'stage': stage.key,
        'since': _day(reached[stage.key]),
        'handler_name': _name(getattr(lead, stage.handler)),
        # Every stage up to this one, with the day it was reached and who had
        # it. A stage passed without a date (a lead older than the stamp, or one
        # moved on before its PO date was filled in) is still a stage passed.
        'journey': [{'stage': s.key, 'on': _day(reached[s.key]), 'by': _name(people[s.key])}
                    for s in STAGES[:STAGE_INDEX[stage.key] + 1]],
    }


class WorksView(APIView):
    """The pipeline around the viewer's own stage — upcoming or completed.

    Every stage is counted in one query, so the strip across the top always adds
    up. Rows come a page per stage: Site Visit alone can hold hundreds of
    customers, so each section shows a page and asks for the next
    (`stage` + `offset`) when the reader wants more.
    """
    permission_classes = [permissions.IsAuthenticated]
    PAGE = 25
    MAX_PAGE = 100

    def get(self, request):
        desk = desk_of(request.user)
        if desk is None:
            return Response({'error': 'Works is for the documentation, accounts and project managers.'},
                            status=status.HTTP_403_FORBIDDEN)
        own_key, module = desk
        own = STAGE_INDEX[own_key]

        def side(i):
            return 'upcoming' if i < own else 'mine' if i == own else 'completed'

        view = (request.query_params.get('view') or 'upcoming').strip().lower()
        if view not in ('upcoming', 'completed'):
            return Response({'error': "view must be 'upcoming' or 'completed'."},
                            status=status.HTTP_400_BAD_REQUEST)

        works = live_leads().exclude(is_lost=True).exclude(status='not_interested')
        search = (request.query_params.get('search') or '').strip()
        if search:
            # Names are matched whole, so "Asha K" finds Asha K; the BDE by
            # username as well, which is what the list shows for a BDE with no
            # name on their account.
            works = (works
                     .annotate(_full_name=Concat('first_name', Value(' '),
                                                 Coalesce('last_name', Value(''))),
                               _bde_name=Concat('bde__first_name', Value(' '), 'bde__last_name'))
                     .filter(Q(_full_name__icontains=search) | Q(phone__icontains=search)
                             | Q(company__icontains=search) | Q(district__icontains=search)
                             | Q(_bde_name__icontains=search) | Q(bde__username__icontains=search)))

        # Prefixed: an alias named after a stage would shadow the relation of the
        # same name (site_visit, project) inside the stage filters.
        tally = works.aggregate(**{f'n_{s.key}': Count('id', filter=s.where) for s in STAGES})
        counts = {s.key: tally[f'n_{s.key}'] for s in STAGES}

        # Nearest to the viewer's own stage first: what reaches them next, or
        # what has only just left them.
        shown = sorted((s for i, s in enumerate(STAGES) if side(i) == view),
                       key=lambda s: abs(STAGE_INDEX[s.key] - own))
        wanted = (request.query_params.get('stage') or '').strip()
        if wanted:
            if wanted not in {s.key for s in shown}:
                return Response({'error': f"'{wanted}' is not one of the {view} stages."},
                                status=status.HTTP_400_BAD_REQUEST)
            shown = [STAGES[STAGE_INDEX[wanted]]]

        def number(name, default, low, high):
            try:
                return max(low, min(high, int(request.query_params.get(name, default))))
            except (TypeError, ValueError):
                return default

        limit = number('limit', self.PAGE, 1, self.MAX_PAGE)
        # Paging is per stage, so an offset only means something with one.
        offset = number('offset', 0, 0, 10 ** 9) if wanted else 0

        groups = []
        for s in shown:
            page = (works.filter(s.where)
                    .select_related('product', 'bde', 'documentation_staff', 'accounts_staff',
                                    'purchase_staff', 'project_manager', 'site_visit',
                                    'project__completed_by')
                    # Latest arrivals first; the id settles ties so pages never
                    # overlap or skip a row.
                    .order_by(F(s.since).desc(nulls_last=True), '-id')[offset:offset + limit])
            rows = [_work(lead, s) for lead in page]
            groups.append({'stage': s.key, 'count': counts[s.key], 'offset': offset,
                           'works': rows, 'has_more': offset + len(rows) < counts[s.key]})

        return Response({
            'desk': {'stage': own_key, 'label': STAGES[own].label, 'module': module},
            'view': view,
            'search': search,
            'stages': [{'key': s.key, 'label': s.label, 'blurb': s.blurb,
                        'handler_label': s.handler_label, 'side': side(i),
                        'count': counts[s.key]} for i, s in enumerate(STAGES)],
            'total': sum(counts[s.key] for i, s in enumerate(STAGES) if side(i) == view),
            'groups': groups,
        })
