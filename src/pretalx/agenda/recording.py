# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms


class BaseRecordingProvider:
    """RecordingProviders should subclass this class.

    Register your procider with pretalx.agenda.signals.register_recording_provider.
    """

    def __init__(self, event):
        self.event = event
        super().__init__()

    def get_recording(self, submission):
        """Returns a dictionary {"iframe": …, "csp_header": …} Both the iframe
        and the csp_header should be strings."""
        raise NotImplementedError
