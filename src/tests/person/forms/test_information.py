import pytest
from django_scopes import scopes_disabled

from pretalx.person.forms import SpeakerInformationForm
from tests.factories import EventFactory, SubmissionTypeFactory, TrackFactory

pytestmark = pytest.mark.unit


@pytest.mark.django_db
def test_speaker_information_form_init_limit_types_queryset():
    """limit_types queryset is scoped to the event's submission types."""
    with scopes_disabled():
        event = EventFactory()
        own_type = SubmissionTypeFactory(event=event)
        SubmissionTypeFactory()  # different event's type

        form = SpeakerInformationForm(event=event)

        queryset = list(form.fields["limit_types"].queryset)
        assert own_type in queryset
        assert set(queryset) == set(event.submission_types.all())


@pytest.mark.django_db
def test_speaker_information_form_init_hides_tracks_when_feature_disabled():
    """When use_tracks is disabled, the limit_tracks field is removed."""
    with scopes_disabled():
        event = EventFactory()
        event.feature_flags["use_tracks"] = False

        form = SpeakerInformationForm(event=event)

    assert "limit_tracks" not in form.fields


@pytest.mark.django_db
def test_speaker_information_form_init_shows_tracks_when_feature_enabled():
    """When use_tracks is enabled, the limit_tracks field is present
    with queryset scoped to the event's tracks."""
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event)
        TrackFactory()  # different event's track

        form = SpeakerInformationForm(event=event)

    assert "limit_tracks" in form.fields
    assert list(form.fields["limit_tracks"].queryset) == [track]


@pytest.mark.django_db
def test_speaker_information_form_save_sets_event():
    """save() sets the event on the instance before saving."""
    with scopes_disabled():
        event = EventFactory()
        data = {
            "title_0": "Info Title",
            "text_0": "Some text",
            "target_group": "accepted",
        }

        form = SpeakerInformationForm(data=data, event=event)
        assert form.is_valid(), form.errors
        info = form.save()

    assert info.event == event
    assert str(info.title) == "Info Title"
    assert info.pk is not None


@pytest.mark.django_db
def test_speaker_information_form_save_with_tracks_and_types():
    """save() correctly associates limit_tracks and limit_types."""
    with scopes_disabled():
        event = EventFactory()
        track = TrackFactory(event=event)
        sub_type = SubmissionTypeFactory(event=event)
        data = {
            "title_0": "Info",
            "text_0": "Text",
            "target_group": "submitters",
            "limit_tracks": [track.pk],
            "limit_types": [sub_type.pk],
        }

        form = SpeakerInformationForm(data=data, event=event)
        assert form.is_valid(), form.errors
        info = form.save()

        assert list(info.limit_tracks.all()) == [track]
        assert list(info.limit_types.all()) == [sub_type]


@pytest.mark.parametrize("target_group", ("submitters", "accepted", "confirmed"))
@pytest.mark.django_db
def test_speaker_information_form_accepts_all_target_groups(target_group):
    """Each valid target_group value is accepted."""
    with scopes_disabled():
        event = EventFactory()
        data = {"title_0": "Title", "text_0": "Text", "target_group": target_group}

        form = SpeakerInformationForm(data=data, event=event)

    assert form.is_valid(), form.errors
