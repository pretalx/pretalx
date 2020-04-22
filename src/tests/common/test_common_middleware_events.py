from django.conf import settings
from django.test import Client, TestCase
from django.utils.timezone import now
from django_scopes import scopes_disabled

from pretalx.event.models import Event, Organiser
from pretalx.person.models import User


class LocaleDeterminationTest(TestCase):
    """
    This test case tests various methods around the properties /
    variations concept.
    """

    @classmethod
    def setUpTestData(cls):
        with scopes_disabled():
            o = Organiser.objects.create(name="Dummy", slug="dummy")
            cls.event = Event.objects.create(
                organiser=o,
                name="Dummy",
                slug="dummy",
                date_from=now(),
                date_to=now(),
                is_public=True,
                locale_array="en",
            )
            cls.TEST_LOCALE = "de" if settings.LANGUAGE_CODE == "en" else "en"
            cls.TEST_LOCALE_LONG = (
                "de-AT" if settings.LANGUAGE_CODE == "en" else "en-NZ"
            )
            cls.user = User.objects.create_user(
                password="dummy", email="dummy@dummy.dummy"
            )

    def test_global_default(self):
        c = Client()
        response = c.get("/orga/login/")
        language = response["Content-Language"]
        self.assertEqual(language, settings.LANGUAGE_CODE)

    def test_browser_default(self):
        c = Client(HTTP_ACCEPT_LANGUAGE=self.TEST_LOCALE)
        response = c.get("/orga/login/")
        language = response["Content-Language"]
        self.assertEqual(language, self.TEST_LOCALE)

        c = Client(HTTP_ACCEPT_LANGUAGE=self.TEST_LOCALE_LONG)
        response = c.get("/orga/login/")
        language = response["Content-Language"]
        self.assertEqual(language, self.TEST_LOCALE)

    def test_unknown_browser_default(self):
        c = Client(HTTP_ACCEPT_LANGUAGE="sjn")
        response = c.get("/orga/login/")
        language = response["Content-Language"]
        self.assertEqual(language, settings.LANGUAGE_CODE)

    def test_cookie_settings(self):
        c = Client()
        cookies = c.cookies
        cookies[settings.LANGUAGE_COOKIE_NAME] = self.TEST_LOCALE
        response = c.get("/orga/login/")
        language = response["Content-Language"]
        self.assertEqual(language, self.TEST_LOCALE)

        cookies[settings.LANGUAGE_COOKIE_NAME] = self.TEST_LOCALE_LONG
        response = c.get("/orga/login/")
        language = response["Content-Language"]
        self.assertEqual(language, self.TEST_LOCALE)

    def test_user_settings(self):
        c = Client()
        self.user.locale = self.TEST_LOCALE
        self.user.save()
        response = c.post(
            "/orga/login/",
            {"login_email": "dummy@dummy.dummy", "login_password": "dummy",},
        )
        self.assertEqual(response.status_code, 302)

        response = c.get("/orga/login/")
        language = response["Content-Language"]
        self.assertEqual(language, self.TEST_LOCALE)

    def test_event_allowed(self):
        self.event.locale_array = "de,en"
        self.event.save()
        c = Client()
        cookies = c.cookies
        cookies[settings.LANGUAGE_COOKIE_NAME] = "de"
        response = c.get("/dummy/")
        language = response["Content-Language"]
        self.assertEqual(language, "de")

    def test_event_fallback_to_short(self):
        self.event.locale_array = "de"
        self.event.locales = ["de"]
        self.event.save()
        c = Client()
        cookies = c.cookies
        cookies[settings.LANGUAGE_COOKIE_NAME] = "de-formal"
        response = c.get("/dummy/")
        language = response["Content-Language"]
        self.assertEqual(language, "de")

    def test_event_fallback_to_long(self):
        self.event.locale_array = "de-formal"
        self.event.save()
        c = Client()
        cookies = c.cookies
        cookies[settings.LANGUAGE_COOKIE_NAME] = "de"
        response = c.get("/dummy/")
        language = response["Content-Language"]
        self.assertEqual(language, "de-formal")

    def test_event_not_allowed(self):
        self.event.locale_array = "en"
        self.event.save()
        c = Client()
        cookies = c.cookies
        cookies[settings.LANGUAGE_COOKIE_NAME] = "de"
        response = c.get("/dummy/")
        language = response["Content-Language"]
        self.assertEqual(language, "en")
