# SPDX-FileCopyrightText: 2026-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
from django.dispatch import receiver

from pretalx.orga.signals import event_copy_data

copied_events = []


@receiver(event_copy_data, dispatch_uid="dummy_app_event_copy_data")
def record_event_copy(sender, other, **kwargs):
    copied_events.append((sender.slug, other))
