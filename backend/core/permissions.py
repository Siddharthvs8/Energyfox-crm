from rest_framework import permissions


def watches_everything(user):
    """The spectator: a view-only account that may open any admin screen.

    Every class below admits it, because it is meant to see what an admin sees.
    That is not a hole: SpectatorReadOnlyMiddleware refuses the request before it
    reaches any of these views unless the method only reads.
    """
    return bool(user and user.is_authenticated and getattr(user, 'is_spectator', False))


class IsAdminOnly(permissions.BasePermission):
    """Only allow admin (is_staff) users — plus the read-only spectator."""
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and
            (request.user.is_staff or watches_everything(request.user))
        )


class IsAdminOrGeneralManager(permissions.BasePermission):
    """Only allow admin (is_staff) or general managers."""
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and
            (request.user.is_staff or request.user.is_general_manager
             or watches_everything(request.user))
        )


class IsAdminOrManager(permissions.BasePermission):
    """Allow admin, general managers, and regular managers."""
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and
            (request.user.is_staff or request.user.is_general_manager or request.user.is_manager
             or watches_everything(request.user))
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
            (u.is_staff or u.is_general_manager or u.is_manager or runs_the_leads_desk(u)
             or watches_everything(u))
        )


class MetaIntegrationAccess(permissions.BasePermission):
    """The Meta integration: admins, plus the leads manager who owns lead sources.

    Its own class rather than widening IsAdminOnly, which also guards user
    administration.
    """
    def has_permission(self, request, view):
        u = request.user
        return bool(
            u and u.is_authenticated and (u.is_staff or runs_the_leads_desk(u)
                                          or watches_everything(u))
        )
