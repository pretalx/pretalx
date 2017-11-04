from django.db import models
from django.utils.translation import ugettext_lazy as _
from urlman import Urls


class Review(models.Model):
    submission = models.ForeignKey(
        to='submission.Submission',
        related_name='reviews',
    )
    user = models.ForeignKey(
        to='person.User',
        related_name='reviews',
    )
    text = models.TextField(
        verbose_name=_('What do you think?'),
        null=True, blank=True,
    )
    score = models.IntegerField(
        null=True, blank=True
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    @classmethod
    def find_missing_reviews(cls, event, user):
        from pretalx.submission.models import SubmissionStates

        return event.submissions.filter(state=SubmissionStates.SUBMITTED) \
            .exclude(reviews__user=user) \
            .exclude(speakers__in=[user])

    class urls(Urls):
        base = '{self.submission.orga_urls.reviews}'
        delete = '{base}/{self.pk}/delete'
