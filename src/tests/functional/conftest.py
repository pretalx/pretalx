import datetime

import pytest
from django.utils.timezone import now

from pretalx.event.models import Event
from pretalx.mail.models import MailTemplate
from pretalx.person.models import EventPermission, User
from pretalx.schedule.models import Room, Schedule, TalkSlot
from pretalx.submission.models import (
    Question, QuestionVariant, Submission, SubmissionType,
)


@pytest.fixture
def event():
    today = datetime.date.today()
    return Event.objects.create(
        name='Fancy testevent', is_public=True, slug='test', email='orga@orga.org',
        date_from=today, date_to=today + datetime.timedelta(days=3)
    )


@pytest.fixture
def other_event():
    return Event.objects.create(name='Boring testevent', is_public=True, slug='test2', email='orga2@orga.org',
                                date_from=datetime.date.today(), date_to=datetime.date.today())


@pytest.fixture
def question(event):
    return Question.objects.create(event=event, question='How old are you?',
                                   variant=QuestionVariant.NUMBER,
                                   required=False)


@pytest.fixture
def user(event):
    return User.objects.create_user('testuser', 'testpassw0rd')


@pytest.fixture
def orga_user(event):
    user = User.objects.create_user('orgauser', 'orgapassw0rd')
    EventPermission.objects.create(user=user, event=event, is_orga=True)
    return user


@pytest.fixture
def other_orga_user(event):
    user = User.objects.create_user('evilorgauser', 'orgapassw0rd', email='evilorgauser@orga.org')
    EventPermission.objects.create(user=user, event=event, is_orga=True)
    return user


@pytest.fixture
def orga_client(orga_user, client):
    client.force_login(orga_user)
    return client


@pytest.fixture
def submission_type(event):
    return SubmissionType.objects.create(name='Workshop', event=event)


@pytest.fixture
def default_submission_type(event):
    return event.cfp.default_type


@pytest.fixture
def speaker():
    return User.objects.create_user('speaker', 'speakerpwd', name='Jane Speaker')


@pytest.fixture
def speaker_client(client, speaker):
    client.force_login(speaker)
    return client


@pytest.fixture
def other_speaker():
    return User.objects.create_user('speaker2', 'speakerpwd', name='Krümelmonster')


@pytest.fixture
def submission(event, speaker, submission_type):
    sub = Submission.objects.create(
        title='A Submission', event=event,
        code='BLAKEKS', submission_type=submission_type,
        description='Some talk description', abstract='Fancy abstract',
        notes='I like cookies', content_locale='en'
    )
    sub.save()
    sub.speakers.add(speaker)
    return sub


@pytest.fixture
def other_submission(event, other_speaker):
    sub = Submission.objects.create(
        title='Albrecht Dürer. Sein Leben, seine Zeit', event=event,
        code='BLAKOKS', submission_type=event.cfp.default_type,
        description='1 guter Talk', abstract='Verstehste?',
        notes='I like cookies A LOT', content_locale='en'
    )
    sub.save()
    sub.speakers.add(other_speaker)
    return sub


@pytest.fixture
def accepted_submission(submission):
    submission.accept()
    return submission


@pytest.fixture
def other_accepted_submission(other_submission):
    other_submission.accept()
    return other_submission


@pytest.fixture
def rejected_submission(submission):
    submission.reject()
    return submission


@pytest.fixture
def confirmed_submission(accepted_submission):
    accepted_submission.confirm()
    return accepted_submission


@pytest.fixture
def other_confirmed_submission(other_accepted_submission):
    other_accepted_submission.confirm()
    return other_accepted_submission


@pytest.fixture
def invitation(event):
    return EventPermission.objects.create(event=event, is_orga=True, invitation_token='testtoken', invitation_email='some@test.mail')


@pytest.fixture
def mail_template(event):
    return MailTemplate.objects.create(event=event, subject='Some Mail', text='Whee mail content!', reply_to='orga@orga.org')


@pytest.fixture(scope='function')
def mail(mail_template, speaker, event):
    return mail_template.to_mail(speaker, event)


@pytest.fixture(scope='function')
def other_mail(mail_template, event, speaker):
    return mail_template.to_mail(speaker, event)


@pytest.fixture
def sent_mail(mail_template, speaker, event):
    mail = mail_template.to_mail(speaker, event)
    mail.send()
    return mail


@pytest.fixture
def room(event):
    return Room.objects.create(event=event, name='Testroom', description='A fancy room', position=2, capacity=50)


@pytest.fixture
def schedule(event):
    return Schedule.objects.create(event=event, version='Test Version', published=now())


@pytest.fixture
def slot(confirmed_submission, room, schedule):
    return TalkSlot.objects.create(start=now(), end=now() + datetime.timedelta(minutes=30), submission=confirmed_submission, room=room, schedule=schedule, is_visible=True)


@pytest.fixture
def other_slot(other_confirmed_submission, room, schedule):
    return TalkSlot.objects.create(start=now(), end=now() + datetime.timedelta(minutes=30), submission=other_confirmed_submission, room=room, schedule=schedule, is_visible=True)


@pytest.fixture
def schedule_schema():
    from lxml import etree
    with open('tests/functional/fixtures/schedule.xsd', 'r') as xsd:
        source = xsd.read()
    schema = etree.XML(source)
    return etree.XMLSchema(schema)
