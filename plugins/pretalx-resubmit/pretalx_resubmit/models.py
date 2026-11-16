from django.db import models


class Resubmission(models.Model):
    """Links a proposal to the proposal in another event it was copied from."""

    submission = models.OneToOneField(
        "submission.Submission",
        on_delete=models.CASCADE,
        related_name="resubmitted_from",
    )
    # Kept when the original is deleted, so the copy stays a plain proposal
    source = models.ForeignKey(
        "submission.Submission",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created = models.DateTimeField(auto_now_add=True)
