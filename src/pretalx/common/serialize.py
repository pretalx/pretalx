from datetime import timedelta


def serialize_duration(minutes):
    duration = timedelta(minutes=minutes)
    days = duration.days
    hours = int(duration.total_seconds() // 3600 - days * 24)
    minutes = int(duration.seconds // 60 % 60)
    fmt = '{:02}'.format(minutes)
    if hours or days:
        fmt = '{:02}:{}'.format(hours, fmt)
        if days:
            fmt = '{}:{}'.format(days, fmt)
    else:
        fmt = '00:{}'.format(fmt)
    return fmt
