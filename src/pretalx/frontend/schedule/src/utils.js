// SPDX-FileCopyrightText: 2020-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// import i18n from 'i18n'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const markdownIt = MarkdownIt({
	html: true,
	linkify: true,
	breaks: true
})

export const renderMarkdown = (text, inline = false) => {
	if (!text) return ''
	try {
		const rendered = inline ? markdownIt.renderInline(text) : markdownIt.render(text)
		return DOMPurify.sanitize(rendered)
	} catch (error) {
		console.error('Error rendering markdown:', error)
		return text
	}
}

export function getCookie (name) {
	const prefix = `${name}=`
	for (const cookie of document.cookie.split(';')) {
		const trimmed = cookie.trim()
		if (trimmed.startsWith(prefix)) {
			return decodeURIComponent(trimmed.slice(prefix.length))
		}
	}
	return null
}

export function getLocalizedString (string, locale) {
	if (!string) return ''
	if (typeof string === 'string') return string
	const lang = locale || 'en'
	return string[lang] || string[lang.split('-')[0]] || string.en || Object.values(string)[0] || ''
}

const checkPropScrolling = (node, prop) => ['auto', 'scroll'].includes(getComputedStyle(node, null).getPropertyValue(prop))
const isScrolling = node => checkPropScrolling(node, 'overflow') || checkPropScrolling(node, 'overflow-x') || checkPropScrolling(node, 'overflow-y')
export function findScrollParent (node) {
	if (!node || node === document.body) return
	if (isScrolling(node)) return node
	return findScrollParent(node.parentNode)
}
export function getPrettyDuration (start, end) {
	let minutes = end.diff(start).shiftTo('minutes').minutes
	if (minutes <= 60) {
		return `${minutes}min`
	}
	const hours = Math.floor(minutes / 60)
	minutes = minutes % 60
	if (minutes) {
		return `${hours}h${minutes}min`
	}
	return `${hours}h`
}

export function timeWithoutAmPm (time, locale) {
	const parts = new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: 'numeric', timeZone: time.zoneName }).formatToParts(time)
	return parts.filter(part => part.type !== 'dayPeriod').map(part => part.value).join('')
}

export function timeAmPm (time, locale) {
	const parts = new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: 'numeric', timeZone: time.zoneName }).formatToParts(time)
	return parts.filter(part => part.type === 'dayPeriod')[0].value
}

export function getSessionTime(session, timezone, locale, hasAmPm) {
	if (hasAmPm) {
		return {
			time: timeWithoutAmPm(session.start.setZone(timezone), locale),
			ampm: timeAmPm(session.start.setZone(timezone), locale)
		}
	} else {
		return {
			time: session.start.setZone(timezone).toLocaleString({ hour: 'numeric', 'minute': 'numeric' })
		}
	}
}

export function isProperSession (session) {
	// breaks and such don't have ids
	return !!session.id
}

export const getLanguageName = (code, locale) => {
	try {
		const lang = locale || 'en'
		const languageNames = new Intl.DisplayNames([lang], { type: 'language' })
		return languageNames.of(code) || code
	} catch {
		return code
	}
}

export async function fetchSchedule(eventUrl, version) {
	let versionPath = ''
	if (version)
		versionPath = `v/${version}/`
	const url = `${eventUrl}schedule/${versionPath}widgets/schedule.json`
	const legacyUrl = `${eventUrl}schedule/${versionPath}widget/v2.json`

	const tryFetch = async (target) => {
		const response = await fetch(target)
		if (!response.ok) throw new Error(`HTTP error ${response.status} for ${target}`)
		return response.json()
	}

	try {
		return await tryFetch(url)
	} catch (e) {
		try {
			return await tryFetch(legacyUrl)
		} catch (e) {
			throw new Error('Failed to fetch schedule from both URLs')
		}
	}
}
