import datetime as dt

import factory
from django.utils.timezone import now


class CachedFileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "common.CachedFile"

    filename = factory.Sequence(lambda n: f"file-{n}.zip")
    content_type = "application/zip"
    expires = factory.LazyFunction(lambda: now() + dt.timedelta(hours=1))
