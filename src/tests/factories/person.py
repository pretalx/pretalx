import factory

from pretalx.person.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    name = factory.Sequence(lambda n: f"User {n}")
    locale = "en"
    timezone = "UTC"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", "testpassword!")
        manager = cls._get_manager(model_class)
        return manager.create_user(*args, password=password, **kwargs)
