from i18nfield.rest_framework import I18nAwareModelSerializer
from rest_framework.serializers import ModelSerializer, SlugRelatedField

from pretalx.api.serializers.speaker import SubmitterSerializer
from pretalx.schedule.models import Schedule, TalkSlot
from pretalx.submission.models import Submission, SubmissionStates


class SlotSerializer(I18nAwareModelSerializer):
    room = SlugRelatedField(slug_field='name', read_only=True)

    class Meta:
        model = TalkSlot
        fields = (
            'room', 'start', 'end',
        )


class SubmissionSerializer(I18nAwareModelSerializer):
    speakers = SubmitterSerializer(many=True)
    submission_type = SlugRelatedField(slug_field='name', read_only=True)
    slot = SlotSerializer(TalkSlot.objects.filter(is_visible=True), read_only=True)

    class Meta:
        model = Submission
        fields = (
            'code', 'speakers', 'title', 'submission_type', 'state', 'abstract',
            'description', 'duration', 'do_not_record', 'content_locale', 'slot',
        )


class ScheduleSerializer(ModelSerializer):
    slots = SubmissionSerializer(Submission.objects.filter(state=SubmissionStates.CONFIRMED), many=True)

    class Meta:
        model = Schedule
        fields = (
            'slots', 'version',
        )
