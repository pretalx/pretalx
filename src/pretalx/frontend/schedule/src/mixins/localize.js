// SPDX-FileCopyrightText: 2026-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// Provides locale-aware getLocalizedString / getLanguageName helpers to
// components. The widget locale is injected from App (provided as
// `widgetLocale`) rather than read from the host page's <html lang>, so
// embedded and web-component mounts use the locale they were configured
// with instead of the surrounding page's language.
import { getLocalizedString, getLanguageName } from '~/utils'

export default {
	inject: {
		widgetLocale: { default: 'en' }
	},
	methods: {
		getLocalizedString (string) {
			return getLocalizedString(string, this.widgetLocale)
		},
		getLanguageName (code) {
			return getLanguageName(code, this.widgetLocale)
		}
	}
}
