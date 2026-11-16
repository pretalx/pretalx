from django.db import models


class PretixCustomer(models.Model):
    """Links a pretalx user to the pretix customer account they logged in with.

    ``identifier`` is the OIDC ``sub`` claim, which pretix also stores as the
    ``customer`` of every order placed while logged in.
    """

    user = models.OneToOneField(
        "person.User", on_delete=models.CASCADE, related_name="pretix_customer"
    )
    identifier = models.CharField(max_length=190, unique=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.identifier


class TicketOverride(models.Model):
    """An organiser has confirmed that this speaker is covered for this event,
    e.g. a complimentary ticket or one bought under another email address."""

    event = models.ForeignKey(
        "event.Event", on_delete=models.CASCADE, related_name="+"
    )
    user = models.ForeignKey("person.User", on_delete=models.CASCADE, related_name="+")
    created_by = models.ForeignKey(
        "person.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"], name="pretix_sso_unique_override"
            )
        ]
