from rest_framework import permissions


class IsAdminOnly(permissions.BasePermission):
    """Only allow admin (is_staff) users."""
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and
            request.user.is_staff
        )


class IsAdminOrGeneralManager(permissions.BasePermission):
    """Only allow admin (is_staff) or general managers."""
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and
            (request.user.is_staff or request.user.is_general_manager)
        )


class IsAdminOrManager(permissions.BasePermission):
    """Allow admin, general managers, and regular managers."""
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and
            (request.user.is_staff or request.user.is_general_manager or request.user.is_manager)
        )


def runs_the_leads_desk(user):
    """The leads manager: the lead book, its campaigns and where leads come from.

    Deliberately not `is_staff` or `is_general_manager` — either of those would
    open every module in the company. The three doors this role needs are opened
    one at a time, here and in the nav.
    """
    return bool(
        user and user.is_authenticated and getattr(user, 'role', '') == 'leads_manager'
    )


class CampaignAccess(permissions.BasePermission):
    """Campaigns: admins and managers as before, plus the leads manager.

    Its own class rather than widening IsAdminOrManager, which also guards the
    AI manager — the leads desk has no business there.
    """
    def has_permission(self, request, view):
        u = request.user
        return bool(
            u and u.is_authenticated and
            (u.is_staff or u.is_general_manager or u.is_manager or runs_the_leads_desk(u))
        )


class MetaIntegrationAccess(permissions.BasePermission):
    """The Meta integration: admins, plus the leads manager who owns lead sources.

    Its own class rather than widening IsAdminOnly, which also guards user
    administration.
    """
    def has_permission(self, request, view):
        u = request.user
        return bool(
            u and u.is_authenticated and (u.is_staff or runs_the_leads_desk(u))
        )
