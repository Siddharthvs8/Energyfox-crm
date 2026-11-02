"""Recording what a bulk update changed.

The signals hear every save(), but queryset.update() writes straight to the
table and sends none, so a bulk path was the one way a change could get past
the trail. One did: a page of leads handed to a BDE with the bulk Assign showed
that BDE on every one of them and nothing on record to say who had done it,
which read as the CRM assigning BDEs by itself.

    with recording(Lead, ids):
        Lead.objects.filter(id__in=ids).update(assigned_to=user)

reads the rows before and after the block, and for each one that changed writes
the entry a save() would have written — named after whoever is making the
request, like any other.
"""
import logging
from contextlib import contextmanager

from .registry import is_audited
from .signals import _record_update

logger = logging.getLogger(__name__)


@contextmanager
def recording(model, pks):
    if not is_audited(model):
        yield
        return
    before = {row.pk: row for row in model.objects.filter(pk__in=list(pks))}
    yield
    for after in model.objects.filter(pk__in=list(before)):
        try:
            _record_update(before[after.pk], after)
        except Exception:
            # As with the signals: a gap in the record, never lost work.
            logger.exception('Could not record a bulk change to %s #%s', model.__name__, after.pk)
