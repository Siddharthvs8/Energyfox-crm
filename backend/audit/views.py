"""The Activity Log, for the two roles that answer for the whole company."""
from django.db.models import Q
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import AuditEntry
from .registry import categories


class AdminOnly(permissions.BasePermission):
    """Admins and super admins, and nobody else.

    Deliberately narrower than `sees_everything`: that includes the spectator,
    and a record of who changed what — including changes to people's roles and
    to money — is not a watching brief. It answers a question about
    accountability, so it is kept to the accounts that carry it.
    """
    message = 'The activity log is for admins and super admins.'

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.role in ('admin', 'superadmin')


class AuditEntrySerializer(serializers.ModelSerializer):
    actor_display = serializers.SerializerMethodField()
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = AuditEntry
        fields = ['id', 'actor', 'actor_name', 'actor_display', 'action', 'action_display',
                  'category', 'model_label', 'object_id', 'object_label',
                  'changes', 'summary', 'created_at']

    def get_actor_display(self, obj):
        # The stored name first: it is what was true when the change was made,
        # and it survives the account being deleted or renamed.
        return obj.actor_name or (obj.actor.username if obj.actor else 'System')


class AuditPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class AuditEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only, permanently.

    An audit trail that can be edited is not one. There is no create, update or
    delete here and there should never be — not even for an admin, who is
    precisely the person whose changes it exists to record.
    """
    serializer_class = AuditEntrySerializer
    permission_classes = [permissions.IsAuthenticated, AdminOnly]
    pagination_class = AuditPagination
    queryset = AuditEntry.objects.all()

    def get_queryset(self):
        qs = AuditEntry.objects.select_related('actor').all()
        params = self.request.query_params

        category = params.get('category')
        if category and category != 'all':
            qs = qs.filter(category=category)

        act = params.get('action')
        if act and act != 'all':
            qs = qs.filter(action=act)

        actor = params.get('actor')
        if actor:
            qs = qs.filter(actor_id=actor)

        # Dates are given as the days a person means, so `date_to` includes the
        # whole of that day rather than stopping at midnight before it.
        date_from, date_to = params.get('date_from'), params.get('date_to')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        search = (params.get('search') or '').strip()
        if search:
            # Across the readable columns, so "Kollam", "raised the price" and
            # a person's name all find something without the searcher having to
            # know which column holds what.
            qs = qs.filter(
                Q(summary__icontains=search)
                | Q(object_label__icontains=search)
                | Q(actor_name__icontains=search)
                | Q(model_label__icontains=search)
            )
        return qs

    @action(detail=False, methods=['get'])
    def filters(self, request):
        """What the filter can offer, and who has actually done something.

        The actor list is built from the log rather than from the user list, so
        it holds the people who appear in it — including any whose account has
        since been closed, who would otherwise vanish from their own trail.
        """
        actors = (AuditEntry.objects.exclude(actor__isnull=True)
                  .values('actor_id', 'actor_name').distinct().order_by('actor_name'))
        seen, unique = set(), []
        for row in actors:
            if row['actor_id'] in seen:
                continue
            seen.add(row['actor_id'])
            unique.append({'id': row['actor_id'], 'name': row['actor_name'] or 'Unknown'})
        return Response({
            'categories': categories(),
            'actions': [{'value': v, 'label': l} for v, l in AuditEntry.ACTIONS],
            'actors': unique,
            'total': AuditEntry.objects.count(),
        })
