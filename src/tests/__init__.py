# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.test import utils
from django_scopes import scopes_disabled

utils.setup_databases = scopes_disabled()(utils.setup_databases)
