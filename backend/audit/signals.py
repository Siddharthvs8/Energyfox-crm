"""Recording the changes, without anyone having to remember to.

Hooked onto the model signals rather than called from the views, because a
trail that has to be called is a trail with holes in it: the one edit nobody
instrumented is the one somebody will come looking for.

The cost is one extra SELECT per update of an audited model, to read the row as
it was before. That is paid only on writes, only on the models in the registry,
and it is what makes "what did it used to say" answerable at all.
"""
import logging

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .context import get_actor
from .models import AuditEntry
from .registry import IGNORED_FIELDS, REDACTED_FIELDS, category_for, is_audited, label_for

logger = logging.getLogger(__name__)

# Where pre_save leaves the old row for post_save to compare against.
_BEFORE = '_audit_before'


def _display(value):
    """A field value as a line of text.

    Long text is cut: a note edited from four paragraphs to five would
    otherwise put both in the log, and nobody reads a diff that size in a list.
    """
    if value is None:
        return None
    if hasattr(value, 'pk'):                 # a related object
        return str(value)
    text = str(value)
    return text if len(text) <= 200 else text[:200] + '…'


def _label(instance):
    try:
        return str(instance)[:200]
    except Exception:
        # __str__ can reach for a relation that is already gone during a
        # cascading delete. A missing label must not cost the entry.
        return f'#{instance.pk}'


def _actor_fields():
    actor = get_actor()
    if actor is None:
        return None, ''
    name = f'{actor.first_name} {actor.last_name}'.strip() or actor.username
    return actor, name[:150]


def _tracked_fields(instance):
    for field in instance._meta.concrete_fields:
        if field.name in IGNORED_FIELDS or field.attname in IGNORED_FIELDS:
            continue
        yield field


def _write(instance, action, changes=None, summary=''):
    actor, actor_name = _actor_fields()
    AuditEntry.objects.create(
        actor=actor, actor_name=actor_name, action=action,
        category=category_for(type(instance)),
        model_label=label_for(type(instance)),
        object_id=str(instance.pk or ''), object_label=_label(instance),
        changes=changes or {}, summary=summary,
    )


@receiver(pre_save)
def remember_previous(sender, instance, **kwargs):
    """Keep the row as it stands, so post_save can say what moved."""
    if not is_audited(sender) or instance.pk is None or instance._state.adding:
        return
    try:
        instance.__dict__[_BEFORE] = sender.objects.filter(pk=instance.pk).first()
    except Exception:
        instance.__dict__[_BEFORE] = None


@receiver(post_save)
def record_save(sender, instance, created, **kwargs):
    if not is_audited(sender):
        return
    try:
        model_name = sender._meta.verbose_name
        if created:
            _write(instance, AuditEntry.CREATED,
                   summary=f'Created {model_name} "{_label(instance)}"')
            return

        before = instance.__dict__.pop(_BEFORE, None)
        if before is None:
            return                       # nothing to compare; not an edit we can describe

        changes = {}
        for field in _tracked_fields(instance):
            old, new = getattr(before, field.attname, None), getattr(instance, field.attname, None)
            # Compared as they will be written, not as objects. A FileField
            # hands back a fresh wrapper each time whose equality is identity,
            # so two empty ones looked like an edit and every save logged one.
            old_text, new_text = _display(old), _display(new)
            if old == new or old_text == new_text:
                continue
            if field.name in REDACTED_FIELDS or field.attname in REDACTED_FIELDS:
                # That it changed is worth recording; what it changed to is not.
                changes[field.name] = {'from': '••••', 'to': '••••'}
                continue
            changes[field.name] = {'from': old_text, 'to': new_text}

        if not changes:
            return                       # a save that changed nothing is not an edit

        named = ', '.join(list(changes)[:4])
        if len(changes) > 4:
            named += f' and {len(changes) - 4} more'
        _write(instance, AuditEntry.UPDATED, changes=changes,
               summary=f'Changed {named} on {model_name} "{_label(instance)}"')
    except Exception:
        # The log must never be the reason a save fails. A missing line is a
        # gap in the record; a raised exception is lost work for the user.
        logger.exception('Could not record an audit entry for %s', sender)


@receiver(post_delete)
def record_delete(sender, instance, **kwargs):
    if not is_audited(sender):
        return
    try:
        _write(instance, AuditEntry.DELETED,
               summary=f'Deleted {sender._meta.verbose_name} "{_label(instance)}"')
    except Exception:
        logger.exception('Could not record a delete for %s', sender)
