# SPDX-FileCopyrightText: 2017-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

import warnings

from django.core.cache import CacheKeyWarning

# We do not support memcached, suppress key warnings
warnings.simplefilter("ignore", CacheKeyWarning)
