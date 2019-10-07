import pytest
from django_scopes import scope

from pretalx.submission.forms import InfoForm


@pytest.mark.django_db
def test_infoform_content_locale_choices(event):
    event.locale_array = "en,de"
    event.submission_locale_array = "en,de,fr"
    event.save()
    with scope(event=event):
        info_form = InfoForm(event)
        assert info_form.fields["content_locale"].choices == [
            ("en", "English"),
            ("de", "German"),
            ("fr", "French"),
        ]
