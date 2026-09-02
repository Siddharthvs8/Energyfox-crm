"""Carrying the request's user into the model signals."""

from .context import clear_actor, set_actor


class AuditActorMiddleware:
    """Stash who is making this request, so the signals can name them.

    Reads the bearer token for API calls the same way the spectator guard does:
    DRF authenticates inside the view, so `request.user` is still anonymous out
    here. Only for writes — a read changes nothing and should not pay to resolve
    a token.

    Always cleared on the way out, including when the view raises. A thread is
    reused for the next request, and inheriting the last user would attribute
    one person's changes to another.
    """

    SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS', 'TRACE'})

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in self.SAFE_METHODS:
            user = getattr(request, 'user', None)
            if not (user and getattr(user, 'is_authenticated', False)):
                from core.middleware import _jwt_user
                user = _jwt_user(request)
            set_actor(user)
        try:
            return self.get_response(request)
        finally:
            clear_actor()
