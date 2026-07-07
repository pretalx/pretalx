// SPDX-FileCopyrightText: 2022-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

import i18next from 'i18next'

export function getLocale () {
	// Normalise the gettext language (e.g. "en_US", "fr") to a BCP-47 tag
	// for Intl.DateTimeFormat.
	return (i18next.language || 'en').replaceAll('_', '-')
}

export function getLocalizedString (string) {
	if (typeof string === 'string') return string
	try {
		return string[i18next.language] || Object.values(string)[0]
	} catch (e) {
		return ""
	}
}
