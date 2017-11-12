from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from i18nfield.fields import I18nCharField

from pretalx.common.choices import Choices
from pretalx.common.mixins import LogMixin
from pretalx.common.urls import EventUrls


def answer_file_path(instance, filename):
    return f'{instance.question.event.slug}/question_uploads/{filename}'


class QuestionManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().exclude(active=False)


class AllQuestionManager(models.Manager):
    pass


class QuestionVariant(Choices):
    NUMBER = 'number'
    STRING = 'string'
    TEXT = 'text'
    BOOLEAN = 'boolean'
    FILE = 'file'
    CHOICES = 'choices'
    MULTIPLE = 'multiple_choice'

    valid_choices = [
        (NUMBER, _('Number')),
        (STRING, _('Text (one-line)')),
        (TEXT, _('Multi-line text')),
        (BOOLEAN, _('Yes/No')),
        (FILE, _('File upload')),
        (CHOICES, _('Choose one from a list')),
        (MULTIPLE, _('Choose multiple from a list'))
    ]


class QuestionTarget(Choices):
    SUBMISSION = 'submission'
    SPEAKER = 'speaker'

    valid_choices = [
        (SUBMISSION, _('per submission')),
        (SPEAKER, _('per speaker')),
    ]


class Question(LogMixin, models.Model):
    event = models.ForeignKey(
        to='event.Event',
        on_delete=models.PROTECT,
        related_name='questions',
    )
    variant = models.CharField(
        max_length=QuestionVariant.get_max_length(),
        choices=QuestionVariant.get_choices(),
        default=QuestionVariant.STRING,
    )
    target = models.CharField(
        max_length=QuestionTarget.get_max_length(),
        choices=QuestionTarget.get_choices(),
        default=QuestionTarget.SUBMISSION,
        verbose_name=_('question type'),
        help_text=_('Do you require an answer from every speaker or for every talk?'),
    )
    question = I18nCharField(
        max_length=200,
        verbose_name=_('question'),
    )
    help_text = I18nCharField(
        null=True, blank=True,
        max_length=200,
        verbose_name=_('help text'),
        help_text=_('Will appear just like this text below the question input field.')
    )
    default_answer = models.TextField(
        null=True, blank=True,
        verbose_name=_('default answer'),
    )
    required = models.BooleanField(
        default=False,
        verbose_name=_('required'),
    )
    position = models.IntegerField(
        default=0,
        verbose_name=_('position'),
    )
    active = models.BooleanField(
        default=True,
        verbose_name=_('active'),
        help_text=_('Inactive questions will no longer be asked.'),
    )
    contains_personal_data = models.BooleanField(
        default=True,
        verbose_name=_('Answers contain personal data'),
        help_text=_('If a user deletes their account, answers of questions for personal data will be removed, too.'),
    )
    objects = QuestionManager()
    all_objects = AllQuestionManager()

    class urls(EventUrls):
        base = '{self.event.cfp.urls.questions}/{self.pk}'
        edit = '{base}/edit'
        delete = '{base}/delete'

    def __str__(self):
        return str(self.question)

    @cached_property
    def grouped_answers(self):
        if self.variant == QuestionVariant.FILE:
            return [
                {'answer': answer, 'count': 1}
                for answer in self.answers.all()
            ]
        elif self.variant in [QuestionVariant.CHOICES, QuestionVariant.MULTIPLE]:
            return self.answers\
                .order_by('options')\
                .values('options', 'options__answer')\
                .annotate(count=models.Count('id'))\
                .order_by('-count')
        else:
            return list(self.answers.order_by('answer').values('answer').annotate(count=models.Count('id')).order_by('-count'))

    @cached_property
    def missing_answers(self):
        from pretalx.person.models import User
        answer_count = self.answers.all().count()
        if self.target == QuestionTarget.SUBMISSION:
            # TODO: if we are still in the submission phase, count all submissions
            # If we are already later in the event, only count accepted submissions here
            return self.event.submissions.count() - answer_count
        elif self.target == QuestionTarget.SPEAKER:
            return User.objects.filter(submissions__event_id=self.event.pk).count() - answer_count

    class Meta:
        ordering = ['position']


class AnswerOption(LogMixin, models.Model):
    question = models.ForeignKey(
        to='submission.Question',
        on_delete=models.PROTECT,
        related_name='options',
    )
    answer = I18nCharField(
        max_length=200,
    )

    @property
    def event(self):
        return self.question.event

    def __str__(self):
        return str(self.answer)


class Answer(LogMixin, models.Model):
    question = models.ForeignKey(
        to='submission.Question',
        on_delete=models.PROTECT,
        related_name='answers',
    )
    submission = models.ForeignKey(
        to='submission.Submission',
        on_delete=models.PROTECT,
        related_name='answers',
        null=True, blank=True,
    )
    person = models.ForeignKey(
        to='person.User',
        on_delete=models.PROTECT,
        related_name='answers',
        null=True, blank=True,
    )
    answer = models.TextField()
    answer_file = models.FileField(
        upload_to=answer_file_path,
        null=True, blank=True,
    )
    options = models.ManyToManyField(
        to='submission.AnswerOption',
        related_name='answers',
    )

    @property
    def event(self):
        return self.question.event

    def __str__(self):
        return self.answer
