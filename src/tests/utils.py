def refresh(instance, **updates):
    """Return a fresh instance from the database, clearing cached_property values.

    Optionally applies field updates and saves before re-fetching.

    Usage::

        event = refresh(event)  # just re-fetch
        event = refresh(event, is_public=True, date_from=tomorrow)  # update + re-fetch
    """
    if updates:
        for attr, value in updates.items():
            setattr(instance, attr, value)
        instance.save()
    return type(instance).objects.get(pk=instance.pk)
