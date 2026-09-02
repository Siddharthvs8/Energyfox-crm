"""Who is making the change, where a signal can reach it.

A model signal knows what changed but not who changed it — it is nowhere near
the request. The request stashes the user here on the way in, and the signals
read it.

Thread-local rather than a global, because a server handles several requests at
once and two admins editing at the same moment must not be recorded as each
other. Cleared on the way out so a worker thread cannot inherit the last
request's user and attribute a management command to whoever happened to be
logged in.
"""
import threading

_state = threading.local()


def set_actor(user):
    _state.actor = user if (user and getattr(user, 'is_authenticated', False)) else None


def get_actor():
    return getattr(_state, 'actor', None)


def clear_actor():
    _state.actor = None


class actor_of:
    """Attribute changes inside this block to `user`.

    For the paths that have no request — a management command, a webhook, a
    scheduled job — where the change is still somebody's doing and the trail
    should say so.
    """

    def __init__(self, user):
        self.user = user
        self.previous = None

    def __enter__(self):
        self.previous = get_actor()
        set_actor(self.user)
        return self

    def __exit__(self, *exc):
        _state.actor = self.previous
        return False
