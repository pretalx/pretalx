from django.db import models
from django.utils.translation import gettext_lazy as _

# Starting colours for common option names; others get one from PALETTE
NAMED_COLORS = {
    "easy": "#2e9d4f",
    "beginner": "#2e9d4f",
    "medium": "#d68a00",
    "intermediate": "#d68a00",
    "hard": "#c0392b",
    "advanced": "#c0392b",
    "mixed": "#7d3cbf",
    "all levels": "#7d3cbf",
}
PALETTE = ["#2471a3", "#16a085", "#b9770e", "#884ea0", "#5d6d7e", "#cb4335"]


def default_color(option, index):
    return NAMED_COLORS.get(
        str(option.answer).strip().lower(), PALETTE[index % len(PALETTE)]
    )


class ColorSettings(models.Model):
    """Which per-proposal choice question colours the session cards."""

    event = models.OneToOneField(
        "event.Event", on_delete=models.CASCADE, related_name="+"
    )
    question = models.ForeignKey(
        "submission.Question",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Colour sessions by"),
    )

    def __str__(self):
        return f"{self.event_id}: {self.question_id}"


class OptionColor(models.Model):
    option = models.OneToOneField(
        "submission.AnswerOption", on_delete=models.CASCADE, related_name="+"
    )
    color = models.CharField(max_length=7)

    def __str__(self):
        return f"{self.option_id}: {self.color}"
