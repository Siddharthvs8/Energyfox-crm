"""One row per change, whoever made it and wherever they made it from.

The CRM already wrote an ``ActivityLog`` line at the moments someone thought to
write one — a lead created, a status moved, a document sent. That is a story of
the business, and it is useful, but it is not a record of what changed: a phone
number corrected, a deal value edited, a role handed out, a price adjusted all
happened silently.

This is the record. It is written by signals rather than by hand (see
``signals.py``), so a change cannot avoid it by arriving down a path nobody
remembered to instrument — which is the failure mode of every audit trail that
depends on being called.
"""
from django.db import models


class AuditEntry(models.Model):
    CREATED, UPDATED, DELETED = 'created', 'updated', 'deleted'
    ACTIONS = [(CREATED, 'Created'), (UPDATED, 'Updated'), (DELETED, 'Deleted')]

    # Who. The name is kept alongside the link because a trail has to stay
    # readable after the account is gone — which is exactly when it gets read.
    actor = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='audit_entries')
    actor_name = models.CharField(max_length=150, blank=True, default='')

    action = models.CharField(max_length=10, choices=ACTIONS, db_index=True)
    # The module this belongs to, for the filter. Stored rather than derived at
    # read time so an entry keeps the category it had when it was written, even
    # if the mapping is re-cut later.
    category = models.CharField(max_length=40, db_index=True)

    model_label = models.CharField(max_length=80, db_index=True)   # 'leads.Lead'
    # A string, so a model with a non-integer key still records cleanly.
    object_id = models.CharField(max_length=40, blank=True, default='')
    # What the record was called at the time. The row it points at may since
    # have been renamed or deleted; the trail should still say what was touched.
    object_label = models.CharField(max_length=200, blank=True, default='')

    # {field: {"from": ..., "to": ...}} — empty on a create or a delete, where
    # the action is the whole story.
    changes = models.JSONField(default=dict, blank=True)
    # One readable line. Also what the search box matches on, so searching does
    # not have to reach into the JSON.
    summary = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'activity log entry'
        verbose_name_plural = 'activity log'
        indexes = [
            # The two ways this is read: newest first within a module, and
            # everything one person did.
            models.Index(fields=['category', '-created_at']),
            models.Index(fields=['actor', '-created_at']),
        ]

    def __str__(self):
        return self.summary or f'{self.action} {self.model_label}'
