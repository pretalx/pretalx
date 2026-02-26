import pytest
from django.urls import reverse
from django_scopes import scopes_disabled

from pretalx.cfp.flow import (
    BaseCfPStep,
    InfoStep,
    ProfileStep,
    QuestionsStep,
    UserStep,
    cfp_session,
    i18n_string,
    serialize_value,
)
from pretalx.person.models import SpeakerProfile
from pretalx.submission.models import SubmissionStates, SubmissionType
from tests.factories import SubmissionFactory, UserFactory
from tests.utils import SimpleSession, make_request

pytestmark = pytest.mark.unit


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("data", "locales", "expected_en"),
    (
        ("Hello", ["en"], "Hello"),
        ({"en": "Hi"}, ["en"], "Hi"),
        ({"en": "Hi", "de": "Hallo"}, ["en", "de"], "Hi"),
        (42, ["en"], ""),
        (None, ["en"], ""),
    ),
    ids=[
        "plain_string",
        "dict_single_locale",
        "dict_multi_locale",
        "non_string_non_dict",
        "none",
    ],
)
def test_i18n_string_returns_lazy_i18n(data, locales, expected_en):
    """i18n_string converts various input types to LazyI18nString with correct English text."""
    result = i18n_string(data, locales)
    assert str(result) == expected_en or result.data.get("en", "") == expected_en


@pytest.mark.django_db
def test_serialize_value_uses_pk_for_model_instances(event):
    result = serialize_value(event)
    assert result == event.pk


@pytest.mark.django_db
def test_cfp_session_creates_empty_session(cfp_event):
    """cfp_session initializes a new session dict with data/initial/files keys."""
    request = make_request(cfp_event)
    request.resolver_match = type("RM", (), {"kwargs": {"tmpid": "abc123"}})()

    session = cfp_session(request)

    assert session == {"data": {}, "initial": {}, "files": {}}
    assert request.session["cfp"]["abc123"] is session


@pytest.mark.django_db
def test_cfp_session_returns_existing_session(cfp_event):
    """cfp_session returns the existing session data for the same tmpid."""
    request = make_request(cfp_event)
    existing = {"data": {"info": {"title": "Test"}}, "initial": {}, "files": {}}
    request.session = SimpleSession(cfp={"abc123": existing})
    request.resolver_match = type("RM", (), {"kwargs": {"tmpid": "abc123"}})()

    session = cfp_session(request)

    assert session["data"]["info"]["title"] == "Test"


@pytest.mark.django_db
def test_base_cfp_step_priority_defaults_to_100(cfp_event):
    """BaseCfPStep.priority defaults to 100 for custom steps."""

    class CustomStep(BaseCfPStep):
        identifier = "custom"
        label = "Custom"

        def is_completed(self, request):
            return False

    step = CustomStep(event=cfp_event)
    assert step.priority == 100
    assert step.is_completed(make_request(cfp_event)) is False


@pytest.mark.django_db
def test_base_cfp_step_is_applicable_returns_true_by_default(cfp_event):
    """BaseCfPStep.is_applicable returns True by default."""

    class CustomStep(BaseCfPStep):
        identifier = "custom"
        label = "Custom"

        def is_completed(self, request):
            return False

    step = CustomStep(event=cfp_event)
    request = make_request(cfp_event)
    assert step.is_applicable(request) is True
    assert step.is_completed(request) is False


@pytest.mark.django_db
def test_base_cfp_step_done_is_noop(cfp_event):
    """BaseCfPStep.done is a no-op for subclasses to override."""

    class CustomStep(BaseCfPStep):
        identifier = "custom"
        label = "Custom"

        def is_completed(self, request):
            return False

    step = CustomStep(event=cfp_event)
    request = make_request(cfp_event)
    assert step.is_completed(request) is False
    assert step.done(request) is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("step_class", "expected_id", "expected_priority"),
    (
        (InfoStep, "info", 0),
        (QuestionsStep, "questions", 25),
        (UserStep, "user", 49),
        (ProfileStep, "profile", 75),
    ),
    ids=["info", "questions", "user", "profile"],
)
def test_step_identifier_and_priority(
    cfp_event, step_class, expected_id, expected_priority
):
    step = step_class(event=cfp_event)
    assert step.identifier == expected_id
    assert step.priority == expected_priority


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("authenticated", "expected"),
    ((False, True), (True, False)),
    ids=["anonymous_applicable", "authenticated_not_applicable"],
)
def test_user_step_is_applicable(cfp_event, cfp_user, authenticated, expected):
    step = UserStep(event=cfp_event)
    user = cfp_user if authenticated else None
    request = make_request(cfp_event, user=user)
    assert step.is_applicable(request) is expected


@pytest.mark.django_db
def test_questions_step_not_applicable_without_questions(cfp_event):
    """QuestionsStep.is_applicable returns False when no questions exist."""
    step = QuestionsStep(event=cfp_event)
    request = make_request(cfp_event)
    request.session = SimpleSession(
        cfp={"tmpid": {"data": {"info": {}}, "initial": {}, "files": {}}}
    )
    request.resolver_match = type("RM", (), {"kwargs": {"tmpid": "tmpid"}})()
    step.request = request

    with scopes_disabled():
        assert step.is_applicable(request) is False


@pytest.mark.django_db
def test_questions_step_applicable_with_questions(cfp_event, submission_question):
    """QuestionsStep.is_applicable returns True when submission questions exist."""
    step = QuestionsStep(event=cfp_event)
    with scopes_disabled():
        sub_type = SubmissionType.objects.filter(event=cfp_event).first()
    request = make_request(cfp_event)
    request.session = SimpleSession(
        cfp={
            "tmpid": {
                "data": {"info": {"submission_type": sub_type.pk}},
                "initial": {},
                "files": {},
            }
        }
    )
    request.resolver_match = type("RM", (), {"kwargs": {"tmpid": "tmpid"}})()
    step.request = request

    with scopes_disabled():
        assert step.is_applicable(request) is True


@pytest.mark.django_db
def test_cfp_flow_steps_order(cfp_event):
    """CfPFlow steps are ordered by priority: info, questions, user, profile."""
    flow = cfp_event.cfp_flow
    identifiers = [s.identifier for s in flow.steps]
    assert identifiers == ["info", "questions", "user", "profile"]


@pytest.mark.django_db
def test_cfp_flow_steps_linked_list(cfp_event):
    """CfPFlow steps are linked: each step has _previous and _next pointers."""
    flow = cfp_event.cfp_flow
    steps = flow.steps

    assert steps[0]._previous is None
    assert steps[0]._next is steps[1]
    assert getattr(steps[-1], "_next", None) is None
    assert steps[-1]._previous is steps[-2]
    for i in range(1, len(steps) - 1):
        assert steps[i]._previous is steps[i - 1]
        assert steps[i]._next is steps[i + 1]


@pytest.mark.django_db
def test_cfp_flow_steps_dict(cfp_event):
    """CfPFlow.steps_dict is keyed by step identifier."""
    flow = cfp_event.cfp_flow
    assert set(flow.steps_dict.keys()) == {"info", "questions", "user", "profile"}
    assert flow.steps_dict["info"].identifier == "info"


@pytest.mark.django_db
def test_cfp_flow_get_field_config_missing_returns_empty(cfp_event):
    """get_field_config returns empty dict for a non-configured field."""
    flow = cfp_event.cfp_flow
    assert flow.get_field_config("info", "nonexistent") == {}


@pytest.mark.django_db
def test_cfp_flow_update_field_config_creates_new_field(cfp_event):
    """update_field_config adds a new field config entry."""
    with scopes_disabled():
        flow = cfp_event.cfp_flow
        flow.update_field_config("info", "title", label="My Title")

        result = flow.get_field_config("info", "title")
    assert result["key"] == "title"
    assert str(result["label"]) == "My Title"


@pytest.mark.django_db
def test_cfp_flow_update_field_config_updates_existing(cfp_event):
    """update_field_config updates an existing field config entry."""
    with scopes_disabled():
        flow = cfp_event.cfp_flow
        flow.update_field_config("info", "title", label="Old Label")
        flow.update_field_config("info", "title", label="New Label")

        result = cfp_event.cfp_flow.get_field_config("info", "title")
    assert str(result["label"]) == "New Label"


@pytest.mark.django_db
def test_cfp_flow_update_field_config_with_help_text(cfp_event):
    """update_field_config sets help_text on new and existing fields."""
    with scopes_disabled():
        flow = cfp_event.cfp_flow
        flow.update_field_config("info", "title", help_text="Enter the title")

        result = flow.get_field_config("info", "title")
    assert str(result["help_text"]) == "Enter the title"


@pytest.mark.django_db
def test_cfp_flow_update_field_config_updates_help_text(cfp_event):
    """update_field_config updates help_text on an existing field."""
    with scopes_disabled():
        flow = cfp_event.cfp_flow
        flow.update_field_config("info", "title", label="Title", help_text="Old help")
        flow.update_field_config("info", "title", help_text="New help")

        result = flow.get_field_config("info", "title")
    assert str(result["help_text"]) == "New help"
    assert str(result["label"]) == "Title"


@pytest.mark.django_db
def test_cfp_flow_update_field_order(cfp_event):
    """update_field_order reorders fields while preserving existing metadata."""
    with scopes_disabled():
        flow = cfp_event.cfp_flow
        flow.update_field_config("info", "title", label="Custom Title")
        flow.update_field_order("info", ["abstract", "title", "description"])

        step_config = cfp_event.cfp_flow.get_step_config("info")
    keys = [f["key"] for f in step_config["fields"]]
    assert keys == ["abstract", "title", "description"]
    title_config = next(f for f in step_config["fields"] if f["key"] == "title")
    assert str(title_config["label"]) == "Custom Title"


@pytest.mark.django_db
def test_cfp_flow_update_field_order_creates_step_if_missing(cfp_event):
    """update_field_order creates the step config if it doesn't exist."""
    with scopes_disabled():
        flow = cfp_event.cfp_flow
        flow.update_field_order("new_step", ["field_a", "field_b"])

        step_config = cfp_event.cfp_flow.get_step_config("new_step")
    keys = [f["key"] for f in step_config["fields"]]
    assert keys == ["field_a", "field_b"]


@pytest.mark.django_db
def test_cfp_flow_reset(cfp_event):
    """CfPFlow.reset clears all customisations."""
    with scopes_disabled():
        flow = cfp_event.cfp_flow
        flow.update_field_config("info", "title", label="Custom")
        flow.reset()
        # Clear the cached_property so the next access re-reads from DB
        del cfp_event.__dict__["cfp_flow"]

    assert cfp_event.cfp_flow.get_field_config("info", "title") == {}


@pytest.mark.django_db
def test_cfp_flow_update_step_header(cfp_event):
    """update_step_header sets title and text for a step."""
    with scopes_disabled():
        flow = cfp_event.cfp_flow
        flow.update_step_header("info", title="Welcome!", text="Please submit.")

        step_config = cfp_event.cfp_flow.get_step_config("info")
    assert str(step_config["title"]) == "Welcome!"
    assert str(step_config["text"]) == "Please submit."


@pytest.mark.django_db
def test_get_next_applicable_skips_non_applicable(cfp_event, cfp_user):
    """get_next_applicable skips steps that are not applicable."""
    with scopes_disabled():
        flow = cfp_event.cfp_flow
        request = make_request(cfp_event, user=cfp_user)
        request.session = SimpleSession(
            cfp={"tmpid": {"data": {"info": {}}, "initial": {}, "files": {}}}
        )
        request.resolver_match = type("RM", (), {"kwargs": {"tmpid": "tmpid"}})()
        for step in flow.steps:
            step.request = request
        info_step = flow.steps_dict["info"]
        next_step = info_step.get_next_applicable(request)
    # User is authenticated, so UserStep is skipped → questions or profile
    assert next_step.identifier != "user"


@pytest.mark.django_db
def test_get_prev_applicable_skips_non_applicable(cfp_event, cfp_user):
    """get_prev_applicable skips steps that are not applicable."""
    with scopes_disabled():
        flow = cfp_event.cfp_flow
        request = make_request(cfp_event, user=cfp_user)
        request.session = SimpleSession(
            cfp={"tmpid": {"data": {"info": {}}, "initial": {}, "files": {}}}
        )
        request.resolver_match = type("RM", (), {"kwargs": {"tmpid": "tmpid"}})()
        for step in flow.steps:
            step.request = request
        profile_step = flow.steps_dict["profile"]
        prev_step = profile_step.get_prev_applicable(request)
    assert prev_step.identifier != "user"


@pytest.mark.django_db
def test_get_step_url_builds_correct_url(cfp_event):
    """get_step_url builds the correct URL for a step."""
    flow = cfp_event.cfp_flow
    info_step = flow.steps_dict["info"]
    info_step.request = make_request(cfp_event)
    info_step.request.resolver_match = type(
        "RM",
        (),
        {"kwargs": {"event": cfp_event.slug, "tmpid": "abc123", "step": "info"}},
    )()
    info_step.request.GET = type(
        "QD", (), {"copy": lambda self: {}, "items": lambda self: []}
    )()

    url = info_step.get_step_url(info_step.request)

    expected = reverse(
        "cfp:event.submit",
        kwargs={"event": cfp_event.slug, "tmpid": "abc123", "step": "info"},
    )
    assert url == expected


@pytest.mark.django_db
def test_info_step_get_form_initial_with_query_params(cfp_event, cfp_track):
    """InfoStep.get_form_initial picks up track and submission_type from GET params."""
    with scopes_disabled():
        step = InfoStep(event=cfp_event)
        sub_type = SubmissionType.objects.filter(event=cfp_event).first()
        request = make_request(cfp_event)
        request.session = SimpleSession(
            cfp={"tmpid": {"data": {}, "initial": {}, "files": {}}}
        )
        request.resolver_match = type("RM", (), {"kwargs": {"tmpid": "tmpid"}})()
        request.GET = {"track": str(cfp_track.pk), "submission_type": str(sub_type.pk)}
        request.access_code = None
        step.request = request

        initial = step.get_form_initial()

    assert initial["track"] == cfp_track
    assert initial["submission_type"] == sub_type


@pytest.mark.django_db
def test_info_step_dedraft_submission_returns_draft(cfp_event, cfp_user):
    """InfoStep.dedraft_submission returns the draft submission when code is in session."""
    with scopes_disabled():
        draft = SubmissionFactory(event=cfp_event, state=SubmissionStates.DRAFT)

        profile, _ = SpeakerProfile.objects.get_or_create(
            user=cfp_user, event=cfp_event
        )
        draft.speakers.add(profile)

        step = InfoStep(event=cfp_event)
        request = make_request(cfp_event, user=cfp_user)
        request.session = SimpleSession(
            cfp={"tmpid": {"data": {}, "initial": {}, "files": {}, "code": draft.code}}
        )
        request.resolver_match = type("RM", (), {"kwargs": {"tmpid": "tmpid"}})()
        step.request = request

        assert step.dedraft_submission == draft


@pytest.mark.django_db
def test_info_step_dedraft_submission_none_for_wrong_user(cfp_event):
    """InfoStep.dedraft_submission returns None when code belongs to another user."""
    with scopes_disabled():
        other_user = UserFactory()
        draft = SubmissionFactory(event=cfp_event, state=SubmissionStates.DRAFT)

        profile, _ = SpeakerProfile.objects.get_or_create(
            user=other_user, event=cfp_event
        )
        draft.speakers.add(profile)

        step = InfoStep(event=cfp_event)
        request = make_request(cfp_event, user=UserFactory())
        request.session = SimpleSession(
            cfp={"tmpid": {"data": {}, "initial": {}, "files": {}, "code": draft.code}}
        )
        request.resolver_match = type("RM", (), {"kwargs": {"tmpid": "tmpid"}})()
        step.request = request

        assert step.dedraft_submission is None
