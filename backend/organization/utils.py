from .models import OrgSettings


def get_org_settings():
    """Return the singleton :class:`OrgSettings` row.

    This is the single-tenant replacement for the old ``connection.tenant``.
    Always returns a row (created on first access).
    """
    return OrgSettings.load()
