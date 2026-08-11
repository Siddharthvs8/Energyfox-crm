"""Cross-cutting request guards."""

from django.http import JsonResponse

# Everything that only reads. Anything else changes state and is refused for a
# view-only account.
SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS', 'TRACE'})

MESSAGE = 'This is a view-only (spectator) account. It cannot make changes.'


def _jwt_user(request):
    """The user behind the request's bearer token, or None.

    DRF authenticates inside the view, so by the time this middleware runs
    `request.user` is still anonymous for an API call. Rather than trust that,
    the token is resolved here — only for write methods, so no read ever pays
    for it. A bad or missing token returns None and the request carries on to
    the view, which produces the proper 401.
    """
    try:
        from rest_framework_simplejwt.authentication import JWTAuthentication
        result = JWTAuthentication().authenticate(request)
    except Exception:
        return None
    return result[0] if result else None


class SpectatorReadOnlyMiddleware:
    """A spectator may read anything in the CRM and change nothing.

    This lives in middleware rather than in a DRF permission class because
    "read-only" has to hold for *every* endpoint — including the many viewsets
    that set their own ``permission_classes`` (which would drop a default one),
    the non-DRF views, and whatever gets added next month. One gate in front of
    all of them cannot be forgotten.

    The role's own visibility rules still live where they belong: the
    ``can_access_*`` gates in ``leads.access`` decide which modules it can open,
    and the ``can_edit_*`` gates return False so the UI never draws a button
    this middleware would then refuse.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in SAFE_METHODS and self._is_spectator(request):
            return JsonResponse({'detail': MESSAGE, 'read_only': True}, status=403)
        return self.get_response(request)

    @staticmethod
    def _is_spectator(request):
        # Session-authenticated callers (Django admin) are already resolved;
        # everyone else arrives with a bearer token and nothing else.
        user = getattr(request, 'user', None)
        if user is None or not getattr(user, 'is_authenticated', False):
            user = _jwt_user(request)
        return bool(user is not None and getattr(user, 'is_spectator', False))
