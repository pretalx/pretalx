from django.conf.urls import include, url
from django.views.generic.base import RedirectView

from pretalx.event.models.event import SLUG_CHARS
from pretalx.orga.views import cards

from .views import (
    admin, auth, cfp, dashboard, event, mails, organiser,
    person, plugins, review, schedule, speaker, submission,
)

app_name = 'orga'
urlpatterns = [
    url('^login/$', auth.LoginView.as_view(), name='login'),
    url('^logout/$', auth.logout_view, name='logout'),
    url('^reset/$', auth.ResetView.as_view(), name='auth.reset'),
    url(r'^reset/(?P<token>\w+)$', auth.RecoverView.as_view(), name='auth.recover'),

    url('^$', RedirectView.as_view(url='event', permanent=False)),
    url('^admin/', admin.AdminDashboard.as_view(), name='admin.dashboard'),
    url('^me$', event.UserSettings.as_view(), name='user.view'),
    url('^me/subuser$', person.SubuserView.as_view(), name='user.subuser'),
    url(r'^invitation/(?P<code>\w+)$', event.InvitationView.as_view(), name='invitation.view'),

    url('^organiser/$', dashboard.DashboardOrganiserListView.as_view(), name='organiser.list'),
    url('^organiser/new$', organiser.OrganiserDetail.as_view(), name='organiser.create'),
    url(f'^organiser/(?P<organiser>[{SLUG_CHARS}]+)/', include([
        url('^$', organiser.OrganiserDetail.as_view(), name='organiser.view'),
        url('^delete$', organiser.OrganiserDelete.as_view(), name='organiser.delete'),
        url('^teams/$', organiser.TeamDetail.as_view(), name='organiser.teams'),
        url('^teams/new$', organiser.TeamDetail.as_view(), name='organiser.teams.create'),
        url('^teams/(?P<pk>[0-9]+)/$', organiser.TeamDetail.as_view(), name='organiser.teams.view'),
        url('^teams/(?P<pk>[0-9]+)/delete$', organiser.TeamDelete.as_view(), name='organiser.teams.delete'),
        url('^teams/(?P<pk>[0-9]+)/tracks$', organiser.TeamTracks.as_view(), name='organiser.teams.tracks'),
        url('^teams/(?P<pk>[0-9]+)/delete/(?P<user_pk>[0-9]+)$', organiser.TeamDelete.as_view(), name='organiser.teams.delete_member'),
        url('^teams/(?P<pk>[0-9]+)/reset/(?P<user_pk>[0-9]+)$', organiser.TeamResetPassword.as_view(), name='organiser.team.password_reset'),
        url('^teams/(?P<pk>[0-9]+)/uninvite$', organiser.TeamUninvite.as_view(), name='organiser.teams.uninvite'),
    ])),

    url('^event/new/$', event.EventWizard.as_view(), name='event.create'),
    url('^event/typeahead/$', event.event_list, name='event.typeahead'),

    url('^event/$', dashboard.DashboardEventListView.as_view(), name='event.list'),
    url(f'^event/(?P<event>[{SLUG_CHARS}]+)/', include([
        url('^$', dashboard.EventDashboardView.as_view(), name='event.dashboard'),
        url('^login/$', auth.LoginView.as_view(), name='event.login'),
        url('^reset/$', auth.ResetView.as_view(), name='event.auth.reset'),
        url(r'^reset/(?P<token>\w+)$', auth.RecoverView.as_view(), name='event.auth.recover'),
        url('^delete$', event.EventDelete.as_view(), name='event.delete'),
        url('^live$', event.EventLive.as_view(), name='event.live'),
        url('^api/users$', person.UserList.as_view(), name='event.user_list'),
        url('^api/urls/$', dashboard.url_list, name='url_list'),

        url('^cfp/questions/$', cfp.CfPQuestionList.as_view(), name='cfp.questions.view'),
        url('^cfp/questions/new$', cfp.CfPQuestionDetail.as_view(), name='cfp.questions.create'),
        url('^cfp/questions/remind$', cfp.CfPQuestionRemind.as_view(), name='cfp.questions.remind'),
        url('^cfp/questions/(?P<pk>[0-9]+)/$', cfp.CfPQuestionDetail.as_view(), name='cfp.question.view'),
        url('^cfp/questions/(?P<pk>[0-9]+)/up$', cfp.question_move_up, name='cfp.questions.up'),
        url('^cfp/questions/(?P<pk>[0-9]+)/down$', cfp.question_move_down, name='cfp.questions.down'),
        url('^cfp/questions/(?P<pk>[0-9]+)/delete$', cfp.CfPQuestionDelete.as_view(), name='cfp.question.delete'),
        url('^cfp/questions/(?P<pk>[0-9]+)/edit$', cfp.CfPQuestionDetail.as_view(), name='cfp.question.edit'),
        url('^cfp/questions/(?P<pk>[0-9]+)/toggle$', cfp.CfPQuestionToggle.as_view(), name='cfp.question.toggle'),
        url('^cfp/text$', cfp.CfPTextDetail.as_view(), name='cfp.text.view'),
        url('^cfp/types/$', cfp.SubmissionTypeList.as_view(), name='cfp.types.view'),
        url('^cfp/types/new$', cfp.SubmissionTypeDetail.as_view(), name='cfp.types.create'),
        url('^cfp/types/(?P<pk>[0-9]+)/$', cfp.SubmissionTypeDetail.as_view(), name='cfp.type.view'),
        url('^cfp/types/(?P<pk>[0-9]+)/delete$', cfp.SubmissionTypeDelete.as_view(), name='cfp.type.delete'),
        url('^cfp/types/(?P<pk>[0-9]+)/default$', cfp.SubmissionTypeDefault.as_view(), name='cfp.type.default'),
        url('^cfp/tracks/$', cfp.TrackList.as_view(), name='cfp.tracks.view'),
        url('^cfp/tracks/new$', cfp.TrackDetail.as_view(), name='cfp.track.create'),
        url('^cfp/tracks/(?P<pk>[0-9]+)/$', cfp.TrackDetail.as_view(), name='cfp.track.view'),
        url('^cfp/tracks/(?P<pk>[0-9]+)/delete$', cfp.TrackDelete.as_view(), name='cfp.track.delete'),

        url('^mails/', include([
            url('^(?P<pk>[0-9]+)/$', mails.MailDetail.as_view(), name='mails.outbox.mail.view'),
            url('^(?P<pk>[0-9]+)/copy$', mails.MailCopy.as_view(), name='mails.outbox.mail.copy'),
            url('^(?P<pk>[0-9]+)/delete$', mails.OutboxPurge.as_view(), name='mails.outbox.mail.delete'),
            url('^(?P<pk>[0-9]+)/send$', mails.OutboxSend.as_view(), name='mails.outbox.mail.send'),
            url('^templates/$', mails.TemplateList.as_view(), name='mails.templates.list'),
            url('^templates/new$', mails.TemplateDetail.as_view(), name='mails.templates.create'),
            url('^templates/(?P<pk>[0-9]+)/$', mails.TemplateDetail.as_view(), name='mails.templates.view'),
            url('^templates/(?P<pk>[0-9]+)/delete$', mails.TemplateDelete.as_view(), name='mails.templates.delete'),
            url('^compose$', mails.ComposeMail.as_view(), name='mails.compose'),
            url('^sent$', mails.SentMail.as_view(), name='mails.sent'),
            url('^outbox/$', mails.OutboxList.as_view(), name='mails.outbox.list'),
            url('^outbox/send$', mails.OutboxSend.as_view(), name='mails.outbox.send'),
            url('^outbox/purge$', mails.OutboxPurge.as_view(), name='mails.outbox.purge'),
        ])),

        url('^submissions/$', submission.SubmissionList.as_view(), name='submissions.list'),
        url('^submissions/new$', submission.SubmissionContent.as_view(), name='submissions.create'),
        url('^submissions/cards/$', cards.SubmissionCards.as_view(), name='submissions.cards'),
        url('^submissions/feed/$', submission.SubmissionFeed(), name='submissions.feed'),
        url('^submissions/statistics/$', submission.SubmissionStats.as_view(), name='submissions.statistics'),
        url(r'^submissions/(?P<code>[\w-]+)/', include([
            url('^$', submission.SubmissionContent.as_view(), name='submissions.content.view'),
            url('^submit$', submission.SubmissionStateChange.as_view(), name='submissions.submit'),
            url('^accept$', submission.SubmissionStateChange.as_view(), name='submissions.accept'),
            url('^reject$', submission.SubmissionStateChange.as_view(), name='submissions.reject'),
            url('^confirm', submission.SubmissionStateChange.as_view(), name='submissions.confirm'),
            url('^withdraw$', submission.SubmissionStateChange.as_view(), name='submissions.withdraw'),
            url('^delete', submission.SubmissionStateChange.as_view(), name='submissions.delete'),
            url('^cancel', submission.SubmissionStateChange.as_view(), name='submissions.cancel'),
            url('^speakers/$', submission.SubmissionSpeakers.as_view(), name='submissions.speakers.view'),
            url('^speakers/add$', submission.SubmissionSpeakersAdd.as_view(), name='submissions.speakers.add'),
            url('^speakers/delete$', submission.SubmissionSpeakersDelete.as_view(), name='submissions.speakers.delete'),
            url('^reviews/$', review.ReviewSubmission.as_view(), name='submissions.reviews'),
            url('^reviews/delete$', review.ReviewSubmissionDelete.as_view(), name='submissions.reviews.submission.delete'),
            url('^feedback/$', submission.FeedbackList.as_view(), name='submissions.feedback.list'),
            url('^toggle_featured$', submission.ToggleFeatured.as_view(), name='submissions.toggle_featured')
        ])),

        url('^speakers/$', speaker.SpeakerList.as_view(), name='speakers.list'),
        url('^speakers/(?P<pk>[0-9]+)/$', speaker.SpeakerDetail.as_view(), name='speakers.view'),
        url('^speakers/(?P<pk>[0-9]+)/reset$', speaker.SpeakerPasswordReset.as_view(), name='speakers.reset'),
        url('^speakers/(?P<pk>[0-9]+)/toggle-arrived$', speaker.SpeakerToggleArrived.as_view(), name='speakers.arrived'),
        url('^info/$', speaker.InformationList.as_view(), name='speakers.information.list'),
        url('^info/new$', speaker.InformationDetail.as_view(), name='speakers.information.create'),
        url('^info/(?P<pk>[0-9]+)/$', speaker.InformationDetail.as_view(), name='speakers.information.view'),
        url('^info/(?P<pk>[0-9]+)/delete$', speaker.InformationDelete.as_view(), name='speakers.information.delete'),

        url('^reviews/$', review.ReviewDashboard.as_view(), name='reviews.dashboard'),

        url('^settings/$', event.EventDetail.as_view(), name='settings.event.view'),
        url('^settings/mail$', event.EventMailSettings.as_view(), name='settings.mail.view'),
        url('^settings/plugins$', plugins.EventPluginsView.as_view(), name='settings.plugins.select'),

        url('^settings/review/$', event.EventReviewSettings.as_view(), name='settings.review'),
        url('^settings/review/phase/(?P<pk>[0-9]+)/up$', event.phase_move_up, name='settings.review.phase.up'),
        url('^settings/review/phase/(?P<pk>[0-9]+)/down$', event.phase_move_down, name='settings.review.phase.down'),
        url('^settings/review/phase/(?P<pk>[0-9]+)/delete$', event.PhaseDelete.as_view(), name='settings.review.phasedelete'),
        url('^settings/review/phase/(?P<pk>[0-9]+)/activate$', event.PhaseActivate.as_view(), name='settings.review.phasedelete'),

        url('^schedule/$', schedule.ScheduleView.as_view(), name='schedule.main'),
        url('^schedule/import/$', schedule.ScheduleImportView.as_view(), name='schedule.import'),
        url('^schedule/export/$', schedule.ScheduleExportView.as_view(), name='schedule.export'),
        url('^schedule/export/trigger$', schedule.ScheduleExportTriggerView.as_view(), name='schedule.export.trigger'),
        url('^schedule/export/download$', schedule.ScheduleExportDownloadView.as_view(), name='schedule.export.download'),
        url('^schedule/release$', schedule.ScheduleReleaseView.as_view(), name='schedule.release'),
        url(r'^schedule/quick/(?P<code>\w+)/$', schedule.QuickScheduleView.as_view(), name='schedule.quick'),
        url('^schedule/reset$', schedule.ScheduleResetView.as_view(), name='schedule.reset'),
        url('^schedule/toggle$', schedule.ScheduleToggleView.as_view(), name='schedule.toggle'),
        url('^schedule/resend_mails$', schedule.ScheduleResendMailsView.as_view(), name='schedule.resend_mails'),
        url('^schedule/rooms/$', schedule.RoomList.as_view(), name='schedule.rooms.list'),
        url('^schedule/rooms/new$', schedule.RoomDetail.as_view(), name='schedule.rooms.create'),
        url('^schedule/rooms/(?P<pk>[0-9]+)/$', schedule.RoomDetail.as_view(), name='schedule.rooms.view'),
        url('^schedule/rooms/(?P<pk>[0-9]+)/delete$', schedule.RoomDelete.as_view(), name='schedule.rooms.delete'),
        url('^schedule/rooms/(?P<pk>[0-9]+)/up$', schedule.room_move_up, name='schedule.rooms.up'),
        url('^schedule/rooms/(?P<pk>[0-9]+)/down$', schedule.room_move_down, name='schedule.rooms.down'),
        url('^schedule/api/talks/$', schedule.TalkList.as_view(), name='schedule.api.talks'),
        url('^schedule/api/talks/(?P<pk>[0-9]+)/$', schedule.TalkUpdate.as_view(), name='schedule.api.update'),
        url(
            '^schedule/api/availabilities/(?P<talkid>[0-9]+)/(?P<roomid>[0-9]+)/$',
            schedule.RoomTalkAvailabilities.as_view(), name='schedule.api.availabilities'
        ),
    ])),
]
