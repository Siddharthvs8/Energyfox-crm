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
