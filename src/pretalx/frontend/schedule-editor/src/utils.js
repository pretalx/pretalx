// SPDX-FileCopyrightText: 2022-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

import i18next from 'i18next'

export function getLocalizedString (string) {
	if (typeof string === 'string') return string
	try {
		return string[i18next.language] || Object.values(string)[0]
	} catch (e) {
		return ""
	}
}
