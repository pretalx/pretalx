# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms
#
# This file contains Apache-2.0 licensed contributions copyrighted by the following contributors:
# SPDX-FileContributor: luto

import rules

from pretalx.event.rules import can_change_event_settings

# Legacy for plugins. TODO remove after v2025.1.0
rules.add_perm("orga.change_settings", can_change_event_settings)
