from django.conf.urls import include, url

from .views import feed, location, schedule, speaker

agenda_urls = [
    url('^(?P<event>\w+)/', include([
        url('^schedule/$', schedule.ScheduleView.as_view(), name='schedule'),
        url('^schedule/changelog$', schedule.ChangelogView.as_view(), name='schedule.changelog'),
        url('^schedule.xml$', schedule.FrabXmlView.as_view(), name='frab-xml'),
        url('^schedule.xcal$', schedule.FrabXCalView.as_view(), name='frab-xcal'),
        url('^schedule.json$', schedule.FrabJsonView.as_view(), name='frab-json'),
        url('^schedule.ics$', schedule.ICalView.as_view(), name='ical'),
        url('^schedule/feed.xml$', feed.ScheduleFeed(), name='feed'),

        url('^location/$', location.LocationView.as_view(), name='location'),
        url('^talk/(?P<slug>\w+)/$', schedule.TalkView.as_view(), name='talk'),
        url('^talk/(?P<slug>\w+)/feedback/$', schedule.FeedbackView.as_view(), name='feedback'),
        url('^speaker/(?P<name>\w+)/$', speaker.SpeakerView.as_view(), name='speaker'),
    ])),
]
