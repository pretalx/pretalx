from pretalx.celery_app import app


@app.task(name="pretalx.schedule.update_unreleased_schedule_changes")
def task_update_unreleased_schedule_changes(event=None, value=None):
    from pretalx.event.models import Event
    from pretalx.schedule.services import update_unreleased_schedule_changes

    event = Event.objects.get(slug=event)
    update_unreleased_schedule_changes(event=event, value=value)
