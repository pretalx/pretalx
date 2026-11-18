from django.db.models import Q
from django_scopes import scope

PLUGIN = "pretalx_fixed_sessions"


def is_active(event):
    return PLUGIN in event.plugin_list


def apply_to(submission):
    """Overwrite the proposal's content with its session type's fixed content.
    Changes the instance only; returns whether anything changed."""
    from .models import FixedSession

    if not submission.submission_type_id:
        return False
    fixed = FixedSession.objects.filter(
        submission_type_id=submission.submission_type_id
    ).first()
    if not fixed or not is_active(submission.event):
        return False
    changed = False
    for field, value in fixed.values().items():
        if getattr(submission, field) != value:
            setattr(submission, field, value)
            changed = True
    return changed


def apply_to_existing(fixed):
    """Write the fixed content to every proposal of its session type, drafts
    and deleted ones included. Returns the number of proposals changed."""
    from pretalx.submission.models import Submission

    event = fixed.submission_type.event
    if not is_active(event):
        return 0
    values = fixed.values()
    # A negated lookup on a nullable column also matches NULL rows
    differs = Q()
    for field, value in values.items():
        differs |= ~Q(**{field: value})
    with scope(event=event):
        # QuerySet.update skips Submission.save(), so the pre_save receiver
        # doesn't run again for each row
        return (
            Submission.all_objects.filter(submission_type=fixed.submission_type)
            .filter(differs)
            .update(**values)
        )
