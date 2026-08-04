"""Who reaches what on the wholesale side.

The B2B roles do different jobs, so the stock register is not one door:

  * Accounts B2B     — runs the whole wholesale business.
  * Store Manager    — keeps the item master, and watches the rest.
  * Store Keeper     — looks up stock and what has been quoted, nothing more.

One matrix, read by both the API permission class and the `me` payload the
sidebar is built from, so the buttons a user sees and the requests the server
accepts cannot disagree.

Plain constants and helpers (no Django imports) so anything may import it.
"""

READ = 'r'
WRITE = 'rw'

# The wholesale modules, named as the client knows them.
MODULES = ('dashboard', 'items', 'suppliers', 'customers', 'proforma', 'dispatch', 'purchases')

# module -> {role: level}. A role absent from a module cannot reach it at all.
MODULE_ACCESS = {
    'dashboard': {'accounts_b2b': WRITE, 'store_manager': READ},
    'items':     {'accounts_b2b': WRITE, 'store_manager': WRITE, 'store_keeper': READ},
    'suppliers': {'accounts_b2b': WRITE},
    'customers': {'accounts_b2b': WRITE, 'store_manager': READ},
    'proforma':  {'accounts_b2b': WRITE, 'store_manager': READ, 'store_keeper': READ},
    'dispatch':  {'accounts_b2b': WRITE, 'store_manager': READ},
    'purchases': {'accounts_b2b': WRITE},
}

# Roles that cross between the retail and wholesale businesses, or buy against
# the register — they are not scoped by the matrix. See IsStockKeeper.
UNRESTRICTED_ROLES = ('coo', 'purchase_staff')


def level_for(user, module):
    """`'rw'`, `'r'`, or None when this user cannot reach the module at all."""
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    if getattr(user, 'is_superuser', False) or getattr(user, 'role', '') in UNRESTRICTED_ROLES:
        return WRITE
    return MODULE_ACCESS.get(module, {}).get(getattr(user, 'role', ''))


def can_read(user, module):
    return level_for(user, module) is not None


def can_write(user, module):
    return level_for(user, module) == WRITE


def access_map(user):
    """Every module this user can reach, as {module: 'r'|'rw'}.

    Sent to the client so the sidebar and the write controls are decided from
    the same table the server enforces.
    """
    out = {}
    for module in MODULES:
        level = level_for(user, module)
        if level:
            out[module] = level
    return out
