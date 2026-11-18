from django.db import models
from django.utils.translation import gettext_lazy as _

# Proposal fields a fixed session sets. track and do_not_record are only set
# when the fixed session has a value for them.
CONTENT_FIELDS = ("title", "abstract", "description")


class FixedSession(models.Model):
    """The content of a core session. Every proposal of its session type gets
    this content on save, replacing what the speaker entered."""

    submission_type = models.OneToOneField(
        "submission.SubmissionType",
        on_delete=models.CASCADE,
        related_name="fixed_session",
    )
    title = models.CharField(max_length=200, verbose_name=_("Session title"))
    abstract = models.TextField(blank=True, verbose_name=_("Abstract"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    track = models.ForeignKey(
        "submission.Track",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Track"),
        help_text=_("Leave empty to let the speaker choose."),
    )
    do_not_record = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Don't record"),
        help_text=_("Leave empty to let the speaker choose."),
    )
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def values(self):
        """The proposal fields this fixed session sets, as {field: value}."""
        result = {field: getattr(self, field) for field in CONTENT_FIELDS}
        if self.track_id:
            result["track_id"] = self.track_id
        if self.do_not_record is not None:
            result["do_not_record"] = self.do_not_record
        return result


class FixedAnswer(models.Model):
    """A core session's answer to a per-proposal question. Shaped like
    pretalx's Answer (question_id, answer, options), so pretalx's question
    fields can show it as their initial value."""

    fixed_session = models.ForeignKey(
        FixedSession, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(
        "submission.Question", on_delete=models.CASCADE, related_name="+"
    )
    # Stored like Answer.answer: the text, "True"/"False" for yes/no
    # questions, the option names for choice questions
    answer = models.TextField(blank=True)
    options = models.ManyToManyField(
        "submission.AnswerOption", blank=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["fixed_session", "question"],
                name="fixed_sessions_unique_answer",
            )
        ]

    def __str__(self):
        return f"{self.fixed_session}: {self.question_id}"
