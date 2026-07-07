// SPDX-FileCopyrightText: 2020-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// Locale-aware time-of-day formatting, shared between the public schedule
// (luxon) and the schedule editor (moment).

export function getHasAmPm (locale) {
	return new Intl.DateTimeFormat(locale, { hour: 'numeric' }).resolvedOptions().hour12
}

export function getTimeString (time, locale, timeZone) {
	return new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: 'numeric', timeZone: timeZone || time.zoneName }).format(time)
}

export function timeWithoutAmPm (time, locale, timeZone) {
	const parts = new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: 'numeric', timeZone: timeZone || time.zoneName }).formatToParts(time)
	return parts.filter(part => part.type !== 'dayPeriod').map(part => part.value).join('')
}

export function timeAmPm (time, locale, timeZone) {
	const parts = new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: 'numeric', timeZone: timeZone || time.zoneName }).formatToParts(time)
	return parts.filter(part => part.type === 'dayPeriod')[0].value
}
