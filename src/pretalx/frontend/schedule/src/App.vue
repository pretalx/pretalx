<!--
SPDX-FileCopyrightText: 2020-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
.pretalx-schedule(:style="{'--scrollparent-width': scrollParentWidth + 'px', '--schedule-max-width': scheduleMaxWidth + 'px', '--pretalx-sticky-date-offset': allDays && allDays.length > 1 ? '48px' : '0px'}", :class="showGrid ? ['grid-schedule'] : ['list-schedule']")
	template(v-if="scheduleError")
		.schedule-notice.error
			.notice-message {{ translationMessages.schedule_load_error || 'An error occurred while loading the schedule. Please try again later.' }}
	template(v-else-if="scheduleEmpty")
		.schedule-notice.info
			.notice-message {{ translationMessages.schedule_empty || 'The schedule is not yet available. Please check back later!' }}
	template(v-else-if="schedule")
		filter-bar(
			:tracks="schedule?.tracks || []",
			:selectedTrackIds="selectedTrackIds",
			:languages="availableLanguages",
			:selectedLanguageCodes="selectedLanguageCodes",
			:filterDoNotRecord="filterDoNotRecord",
			:searchQuery="searchQuery",
			:favsCount="favs.length",
			:onlyFavs="onlyFavs",
			:inEventTimezone="inEventTimezone",
			v-model:currentTimezone="currentTimezone",
			:scheduleTimezone="schedule.timezone",
			:userTimezone="userTimezone",
			:isMobile="isMobile",
			:translationMessages="translationMessages",
			@openFilter="$refs.filterBottomSheet?.showModal()",
			@toggleFavs="toggleFavs",
			@saveTimezone="saveTimezone"
		)
		.days-wrapper
			bunt-tabs.days(v-if="allDays && allDays.length > 1", v-model="currentDay", ref="tabs" :class="showGrid? ['grid-tabs'] : ['list-tabs']")
				bunt-tab(v-for="day in allDays", :id="day.toISODate()", :header="day.toLocaleString(dateFormat)", @selected="onTabSelected(day)")
		template(v-if="sessions.length")
			grid-schedule-wrapper(v-if="showGrid",
				ref="gridScheduleWrapper",
				:sessions="sessions",
				:rooms="rooms",
				:days="days",
				:currentDay="currentDay",
				:now="now",
				:hasAmPm="hasAmPm",
				:timezone="currentTimezone",
				:locale="locale",
				:scrollParent="scrollParent",
				:favs="favs",
				:onHomeServer="onHomeServer",
				@changeDay="setCurrentDay($event)",
				@fav="fav($event)",
				@unfav="unfav($event)")
			linear-schedule(v-else,
				ref="linearSchedule",
				:sessions="sessions",
				:rooms="rooms",
				:currentDay="currentDay",
				:now="now",
				:hasAmPm="hasAmPm",
				:timezone="currentTimezone",
				:locale="locale",
				:scrollParent="scrollParent",
				:favs="favs",
				:onHomeServer="onHomeServer",
				@changeDay="setCurrentDay($event)",
				@fav="fav($event)",
				@unfav="unfav($event)")
			jump-to-now(:visible="showJumpToNow", :label="translationMessages.jump_to_now || 'Jump to now'", @jump="jumpToNow", @dismiss="dismissJumpToNow")
		.schedule-notice.filtered-empty(v-else)
			.notice-message {{ translationMessages.no_matching_sessions || 'No sessions match your current filters.' }}
			button.clear-filters-button(@click="clearAllFilters") {{ translationMessages.clear_filters || 'Clear filters' }}
	bunt-progress-circular(v-else, size="huge", :page="true")
	.error-messages(v-if="errorMessages.length")
		.error-message(v-for="message in errorMessages", :key="message")
			.btn.btn-danger(@click="errorMessages = errorMessages.filter(m => m !== message)") x
			div.message {{ message }}
	#bunt-teleport-target(ref="teleportTarget")
	filter-bottom-sheet(
		ref="filterBottomSheet",
		:tracks="schedule?.tracks || []",
		:selectedTrackIds="selectedTrackIds",
		:languages="availableLanguages",
		:selectedLanguageCodes="selectedLanguageCodes",
		:tags="availableTags",
		:selectedTagIds="selectedTagIds",
		:hasNonRecordedSessions="hasNonRecordedSessions",
		:filterDoNotRecord="filterDoNotRecord",
		:searchQuery="searchQuery",
		:isMobile="isMobile",
		:translationMessages="translationMessages",
		@trackToggled="onTrackToggled",
		@languageToggled="onLanguageToggled",
		@tagToggled="onTagToggled",
		@doNotRecordToggled="onDoNotRecordToggled",
		@searchQueryChange="onSearchQueryChange",
		@clearAll="clearAllFilters"
	)
	session-modal(
		ref="sessionModal",
		:modalContent="modalContent",
		:currentTimezone="currentTimezone",
		:locale="locale",
		:hasAmPm="hasAmPm",
		:now="now",
		:onHomeServer="onHomeServer",
		:isMultilang="isMultilang",
		@toggleFav="favs.includes(modalContent?.contentObject.id) ? unfav(modalContent.contentObject.id) : fav(modalContent.contentObject.id)",
		@showSpeaker="showSpeakerDetails",
		@fav="fav($event)",
		@unfav="unfav($event)"
	)
	a(href="https://pretalx.com", target="_blank", v-if="!onHomeServer").powered-by powered by
		span.pretalx(href="https://pretalx.com", target="_blank") pretalx
</template>
<script>
import { computed } from 'vue'
import { DateTime, Settings } from 'luxon'
import LinearSchedule from '~/components/LinearSchedule'
import GridScheduleWrapper from '~/components/GridScheduleWrapper'
import FavButton from '~/components/FavButton'
import Session from '~/components/Session'
import SessionModal from '~/components/SessionModal'
import FilterBar from '~/components/FilterBar'
import FilterBottomSheet from '~/components/FilterBottomSheet'
import JumpToNow from '~/components/JumpToNow'
import { findScrollParent, getLocalizedString, getSessionTime, fetchSchedule } from '~/utils'

export default {
	name: 'PretalxSchedule',
	components: { FavButton, LinearSchedule, GridScheduleWrapper, Session, SessionModal, FilterBar, FilterBottomSheet, JumpToNow },
	provide () {
		return {
			eventUrl: this.eventUrl,
			widgetLocale: computed(() => this.locale || 'en'),
			remoteApiUrl: computed(() => this.remoteApiUrl),
			translationMessages: computed(() => this.translationMessages),
			buntTeleportTarget: computed(() => this.$refs.teleportTarget),
			onSessionLinkClick: (event, session) => {
				if (this.onHomeServer) return
				event.preventDefault()

				this.showSessionDetails(session, event)
			}
		}
	},
	props: {
		eventUrl: String,
		locale: String,
		format: {
			type: String,
			default: 'grid'
		},
		version: {
			type: String,
			default: ''
		},
		// List the data that should be displayed, as comma-separated strings
		dateFilter: {
			type: String,
			default: ''
		},
		roomFilter: {
			type: String,
			default: ''
		}
	},
	data () {
		return {
			getSessionTime,
			scrollParentWidth: Infinity,
			schedule: null,
			userTimezone: null,
			now: DateTime.now(),
			currentDay: null,
			currentTimezone: null,
			favs: [],
			selectedTrackIds: [],
			selectedLanguageCodes: [],
			selectedTagIds: [],
			filterDoNotRecord: false,
			searchQuery: '',
			updatingFromScroll: false,
			onlyFavs: false,
			scheduleError: false,
			scheduleEmpty: false,
			onHomeServer: false,
			loggedIn: false,
			apiUrl: null,
			translationMessages: {},
			errorMessages: [],
			displayDates: this.dateFilter?.split(',').filter(d => d.length === 10) || [],
			displayRooms: this.roomFilter?.split(',').filter(d => d.length > 0) || [],
			modalContent: null,
			versionPollInterval: null,
			nowInterval: null,
			parentPollTimeout: null,
			isUnmounted: false,
			jumpToNowDismissed: false,
			initialRenderComplete: false,
		}
	},
	computed: {
		scheduleMaxWidth () {
			return this.schedule ? Math.min(this.scrollParentWidth, 78 + this.schedule.rooms.length * 650) : this.scrollParentWidth
		},
		showGrid () {
			// Changes to the 710px cutoff must also be reflected in the static/agenda/_agenda.css file in pretalx-core
			return this.scrollParentWidth > 710 && this.format !== 'list' // if we can't fit two rooms together, switch to list
		},
		roomsLookup () {
			if (!this.schedule) return {}
			return this.schedule.rooms.reduce((acc, room) => { acc[room.id] = room; return acc }, {})
		},
		tracksLookup () {
			if (!this.schedule) return {}
			return this.schedule.tracks.reduce((acc, t) => { acc[t.id] = t; return acc }, {})
		},
		filteredTracks () {
			if (this.selectedTrackIds.length === 0 || !this.schedule?.tracks) return []
			return this.schedule.tracks.filter(t => this.selectedTrackIds.includes(t.id))
		},
		availableLanguages () {
			if (!this.schedule?.talks) return []
			const languageSet = new Set()
			for (const talk of this.schedule.talks) {
				if (talk.content_locale) {
					languageSet.add(talk.content_locale)
				}
			}
			return Array.from(languageSet).sort()
		},
		isMultilang () {
			return this.availableLanguages.length > 1
		},
		filteredLanguages () {
			if (this.selectedLanguageCodes.length === 0) return []
			return this.selectedLanguageCodes.filter(code => this.availableLanguages.includes(code))
		},
		availableTags () {
			return this.schedule?.tags || []
		},
		hasNonRecordedSessions () {
			if (!this.schedule?.talks) return false
			return this.schedule.talks.some(t => t.do_not_record)
		},
		isMobile () {
			return this.scrollParentWidth <= 768
		},
		speakersLookup () {
			if (!this.schedule) return {}
			return this.schedule.speakers.reduce((acc, s) => { acc[s.code] = s; return acc }, {})
		},
		sessions () {
			if (!this.schedule || !this.currentTimezone) return
			const sessions = []
			for (const session of this.schedule.talks.filter(s => s.start)) {
				if (this.onlyFavs && !this.favs.includes(session.code)) continue
				if (this.filteredTracks && this.filteredTracks.length && !this.filteredTracks.find(t => t.id === session.track)) continue
				if (this.filteredLanguages && this.filteredLanguages.length && !this.filteredLanguages.includes(session.content_locale)) continue

				if (this.searchQuery) {
					const searchLower = this.searchQuery.toLowerCase()
					const titleText = getLocalizedString(session.title, this.locale) || ''
					const titleMatch = titleText.toLowerCase().includes(searchLower)
					const speakerMatch = session.speakers?.some(code => {
						const speaker = this.speakersLookup[code]
						return speaker?.name?.toLowerCase().includes(searchLower)
					})
					if (!titleMatch && !speakerMatch) continue
				}

				if (this.selectedTagIds.length && session.tags) {
					if (!this.selectedTagIds.some(tagId => session.tags.includes(tagId))) continue
				}

				if (this.filterDoNotRecord && !session.do_not_record) continue

				const start = DateTime.fromISO(session.start)
				if (this.displayDates?.length && !this.displayDates.includes(start.setZone(this.schedule.timezone).toISODate())) continue
				if (this.displayRooms?.length && !this.displayRooms.includes(session.room.toString())) continue
				sessions.push({
					id: session.code,
					title: session.title,
					abstract: session.abstract,
					do_not_record: session.do_not_record,
					content_locale: session.content_locale,
					start: start,
					end: DateTime.fromISO(session.end),
					speakers: session.speakers?.map(s => this.speakersLookup[s]),
					track: this.tracksLookup[session.track],
					room: this.roomsLookup[session.room]
				})
			}
			sessions.sort((a, b) => a.start.diff(b.start))
			return sessions
		},
		rooms () {
			return this.schedule.rooms.filter(r => this.sessions.some(s => s.room === r))
		},
		days () {
			if (!this.sessions) return
			let days = []
			for (const session of this.sessions) {
				const day = session.start.setZone(this.currentTimezone).startOf('day')
				if (!days.find(d => d.ts === day.ts)) days.push(day)
			}
			days.sort((a, b) => a.diff(b))
			return days
		},
		allDays () {
			if (!this.schedule?.talks || !this.currentTimezone) return []
			const days = []
			for (const talk of this.schedule.talks) {
				if (!talk.start) continue
				const start = DateTime.fromISO(talk.start)
				if (this.displayDates?.length && !this.displayDates.includes(start.setZone(this.schedule.timezone).toISODate())) continue
				const day = start.setZone(this.currentTimezone).startOf('day')
				if (!days.find(d => d.ts === day.ts)) days.push(day)
			}
			days.sort((a, b) => a.diff(b))
			return days
		},
		inEventTimezone () {
			if (!this.schedule?.talks?.length) return false
			return DateTime.local().offset === DateTime.local({ zone: this.schedule.timezone }).offset
		},
		dateFormat () {
			const format = { day: 'numeric', month: 'short' }
			if (this.showGrid) {
				// Mobile schedules always omit the weekday to preserve space, for others, we start
				// shortening the weekday if the schedule gets unwieldy (but we shorten the month name first)
				if (this.allDays && (!this.allDays.length || this.allDays.length <= 7)) {
					format.weekday = 'long'
				} else {
					format.weekday = 'short'
				}
			}
			if ((this.allDays && this.allDays.length <= 5) || (this.showGrid && this.schedule && this.schedule.rooms.length > 2)) {
				// If we have fewer than five days or if we're on a sizeable grid schedule, we can show the long month name
				format.month = 'long'
			}
			return format
		},
		hasAmPm () {
			return new Intl.DateTimeFormat(this.locale, {hour: 'numeric'}).resolvedOptions().hour12
		},
		hasNow () {
			// Check if "now" is within the schedule timespan
			if (!this.sessions || !this.sessions.length) return false
			const firstSession = this.sessions[0]
			const lastSession = this.sessions[this.sessions.length - 1]
			return this.now >= firstSession.start && this.now <= lastSession.end
		},
		showJumpToNow () {
			return this.hasNow && !this.jumpToNowDismissed
		},
		eventSlug () {
			let url = ''
			if (this.eventUrl.startsWith('http')) {
				url = new URL(this.eventUrl)
			} else {
				url = new URL('http://example.org/' + this.eventUrl)
			}
			return url.pathname.replace(/\//g, '')
		},
		remoteApiUrl () {
			if (!this.eventUrl) return ''
			const eventUrlObj = new URL(this.eventUrl)
			return `${eventUrlObj.protocol}//${eventUrlObj.host}/api/events/${this.eventSlug}/`
		},
	},
	watch: {
		currentTimezone () {
			// When timezone changes, select the first day
			this.$nextTick(() => {
				this.setCurrentDay(this.days[0])
			})
		}
	},
	async created () {
		Settings.defaultLocale = this.locale
		this.userTimezone = DateTime.local().zoneName

		try {
			this.schedule = await fetchSchedule(this.eventUrl, this.version)
		} catch (e) {
			this.scheduleError = true
			return
		}
		if (!this.schedule.talks.length) {
			this.scheduleEmpty = true
			return
		}
		this.currentTimezone = localStorage.getItem(`${this.eventSlug}_timezone`)
		this.currentTimezone = [this.schedule.timezone, this.userTimezone].includes(this.currentTimezone) ? this.currentTimezone : this.schedule.timezone
		this.currentDay = this.days[0].toISODate()
		this.now = DateTime.local({ zone: this.currentTimezone })
		this.nowInterval = setInterval(() => this.now = DateTime.local({ zone: this.currentTimezone }), 30000)
		if (!this.scrollParentResizeObserver) {
			await this.$nextTick()
			this.onWindowResize()
		}

		// set API URL before loading favs
		this.apiUrl = window.location.origin + '/api/events/' + this.eventSlug + '/'
		this.favs = this.pruneFavs(await this.loadFavs(), this.schedule)


		this.versionPollInterval = setInterval(() => {
			this.checkForScheduleUpdate()
		},  5 * 60 * 1000)

		this.$nextTick(() => {
			this.initialRenderComplete = true
		})
	},
	async mounted () {
		// We block until we have either a regular parent or a shadow DOM parent
		await new Promise((resolve) => {
			const poll = () => {
				if (this.isUnmounted) return resolve()
				if (this.$el.parentElement || this.$el.getRootNode().host) return resolve()
				this.parentPollTimeout = setTimeout(poll, 100)
			}
			poll()
		})
		if (this.isUnmounted) return
		this.scrollParent = findScrollParent(this.$el.parentElement || this.$el.getRootNode().host)
		if (this.scrollParent) {
			this.scrollParentResizeObserver = new ResizeObserver(this.onScrollParentResize)
			this.scrollParentResizeObserver.observe(this.scrollParent)
			this.scrollParentWidth = this.scrollParent.offsetWidth
		} else { // scrolling document
			window.addEventListener('resize', this.onWindowResize)
			this.onWindowResize()
		}
		// Detect if we're on the home server by comparing origins
		if (this.eventUrl) {
			try {
				const eventOrigin = new URL(this.eventUrl, window.location.origin).origin
				this.onHomeServer = eventOrigin === window.location.origin
			} catch {
				this.onHomeServer = false
			}
		}
		// Check for logged-in user (only relevant on home server)
		if (document.body.dataset.pretalxLoggedIn === 'true') {
			this.loggedIn = true
		}
		// Fetch translation messages
		if (this.eventUrl) {
			try {
				const lang = this.locale?.split('-')[0] || 'en'
				const baseUrl = this.eventUrl.endsWith('/') ? this.eventUrl : `${this.eventUrl}/`
				const messagesUrl = `${baseUrl}schedule/widget/messages.json?lang=${lang}`
				const response = await fetch(messagesUrl)
				if (response.ok) {
					const messages = await response.json()
					if (messages && typeof messages === 'object') {
						this.translationMessages = messages
					}
				}
			} catch {
				// Silently fail - fallback English strings will be used
			}
		}
	},
	beforeUnmount () {
		this.isUnmounted = true
		if (this.parentPollTimeout) {
			clearTimeout(this.parentPollTimeout)
			this.parentPollTimeout = null
		}
		if (this.versionPollInterval) {
			clearInterval(this.versionPollInterval)
			this.versionPollInterval = null
		}
		if (this.nowInterval) {
			clearInterval(this.nowInterval)
			this.nowInterval = null
		}
	},
	methods: {
		setCurrentDay (day) {
			// Find best match among days, because timezones can muddle this
			// This is called from scroll detection - should not trigger auto-scroll
			const matchingDays = this.days.filter(d => d.ts === day.ts)
			if (matchingDays.length) {
				this.updatingFromScroll = true
				this.currentDay = matchingDays[0].toISODate()
				this.$nextTick(() => {
					this.updatingFromScroll = false
				})
			} else {
				const isoMatchingDays = this.days.filter(d => d.toISODate() === day.toISODate())
				if (isoMatchingDays.length) {
					this.updatingFromScroll = true
					this.currentDay = isoMatchingDays[0].toISODate()
					this.$nextTick(() => {
						this.updatingFromScroll = false
					})
				}
			}
		},
		onTabSelected (day) {
			if (this.updatingFromScroll || !this.initialRenderComplete) {
				return
			}
			this.changeDay(day)
		},
		changeDay (day) {
			this.currentDay = day.startOf('day').toISODate()
			// Manually trigger scroll in schedule components
			if (this.$refs.gridScheduleWrapper && this.$refs.gridScheduleWrapper.changeDay) {
				this.$refs.gridScheduleWrapper.changeDay(day.toISODate())
			}
			if (this.$refs.linearSchedule && this.$refs.linearSchedule.changeDay) {
				this.$refs.linearSchedule.changeDay(day.toISODate())
			}
		},
		onWindowResize () {
			this.scrollParentWidth = document.body.offsetWidth
		},
		saveTimezone () {
			localStorage.setItem(`${this.eventSlug}_timezone`, this.currentTimezone)
		},
		onScrollParentResize (entries) {
			this.scrollParentWidth = entries[0].contentRect.width
		},
		async remoteApiRequest (path, method, data) {
			const eventUrlObj = new URL(this.eventUrl)
			const baseUrl = `${eventUrlObj.protocol}//${eventUrlObj.host}/api/events/${this.eventSlug}/`
			return this.apiRequest(path, method, data, baseUrl)
		},
		async apiRequest (path, method, data, baseUrl) {
			const base = baseUrl || this.apiUrl
			const url = `${base}${path}`
			const headers = new Headers()
			if (this.onHomeServer) {
				headers.append('Content-Type', 'application/json')
			}
			if (method === 'POST' || method === 'DELETE') headers.append('X-CSRFToken', document.cookie.split('pretalx_csrftoken=').pop().split(';').shift())
			const response = await fetch(url, {
				method,
				headers,
				body: JSON.stringify(data),
				credentials: this.onHomeServer ? 'same-origin' : 'omit'
			})
			if (!response.ok) {
				throw new Error(`HTTP error! status: ${response.status}`)
			}
			return response.json()
		},
		async loadFavs () {
			const data = localStorage.getItem(`${this.eventSlug}_favs`)
			let favs = []
			if (data) {
				try {
					favs = JSON.parse(data) || []
				} catch {
					localStorage.setItem(`${this.eventSlug}_favs`, '[]')
				}
			}
			if (this.loggedIn) {
				const localFavs = favs
				try {
					favs = await this.apiRequest('submissions/favourites/', 'GET').then(data => {
						const toFav = localFavs.filter(e => !data.includes(e))
						toFav.forEach(e => this.apiRequest(`submissions/${e}/favourite/`, 'POST').catch())
						return data
					}).catch(e => {
						this.pushErrorMessage(this.translationMessages.favs_not_saved)
						return localFavs
					})
				} catch (e) {
					this.pushErrorMessage(this.translationMessages.favs_not_saved)
					favs = localFavs
				}
			}
			return favs
		},
		pushErrorMessage (message) {
			if (!message || !message.length) return
			if (this.errorMessages.includes(message)) return
			this.errorMessages.push(message)
		},
		pruneFavs (favs, schedule) {
			if (!Array.isArray(favs)) return []
			const talks = schedule.talks || []
			const talkIds = talks.map(e => e.code)
			// we're not pushing the changed list to the server, as if a talk vanished but will appear again,
			// we want it to still be faved
			return favs.filter(e => talkIds.includes(e))
		},
		saveFavs () {
			localStorage.setItem(`${this.eventSlug}_favs`, JSON.stringify(this.favs))
		},
		fav (id) {
			if (!this.favs.includes(id)) {
				this.favs.push(id)
				this.saveFavs()
			}
			if (this.loggedIn) {
				this.apiRequest(`submissions/${id}/favourite/`, 'POST').catch(e => {
					this.pushErrorMessage(this.translationMessages.favs_not_saved)
				})
			} else {
				this.pushErrorMessage(this.translationMessages.favs_not_logged_in)
			}
		},
		unfav (id) {
			this.favs = this.favs.filter(elem => elem !== id)
			this.saveFavs()
			if (this.loggedIn) {
				this.apiRequest(`submissions/${id}/favourite/`, 'DELETE').catch(e => {
					this.pushErrorMessage(this.translationMessages.favs_not_saved)
				})
			} else {
				this.pushErrorMessage(this.translationMessages.favs_not_logged_in)
			}
			if (!this.favs.length) this.onlyFavs = false
		},
		async fetchSpeakerApiContentIfNeeded (speakerCode) {
			const speakerObj = this.speakersLookup[speakerCode]
			if (!speakerObj) {
				console.warn(`Speaker with code ${speakerCode} not found in speakersLookup.`)
				return
			}

			if (speakerObj.apiContent || speakerObj.isLoadingApiContent) {
				return // Already fetched or currently fetching
			}

			speakerObj.isLoadingApiContent = true
			try {
				const apiData = await this.remoteApiRequest(`speakers/${speakerCode}/?expand=answers.question`, 'GET')
				speakerObj.apiContent = apiData
			} catch (e) {
				console.error(`Failed to fetch API content for speaker ${speakerCode}:`, e)
				// Potentially set an error flag on speakerObj if needed for UI
			} finally {
				speakerObj.isLoadingApiContent = false
			}
		},
		async showSpeakerDetails(speaker, ev) {
			ev.preventDefault()
			const speakerObj = this.speakersLookup[speaker.code];
			if (!speakerObj) {
				console.warn(`Speaker ${speaker.code} not found for details view.`);
				return;
			}

			const speakerSessions = this.sessions.filter(session =>
				session.speakers?.some(s => s.code === speaker.code)
			)

			// Show speaker immediately with loading state
			this.modalContent = {
				contentType: 'speaker',
				contentObject: {
					...speakerObj,
					sessions: speakerSessions.map(s => ({...s, faved: this.favs.includes(s.id)})),
					isLoading: !speakerObj.apiContent
				}
			}
			this.$refs.sessionModal?.showModal()

			// Attempt to fetch/refresh speaker's apiContent.
			// The helper method handles "already fetched" or "currently fetching" internally.
			await this.fetchSpeakerApiContentIfNeeded(speaker.code)

			// After the fetch attempt, speakerObj in speakersLookup might have been updated.
			// Re-set modalContent to reflect the latest state and turn off modal's isLoading.
			if (this.modalContent && this.modalContent.contentType === 'speaker' && this.modalContent.contentObject.code === speaker.code) {
				this.modalContent = {
					contentType: 'speaker',
					contentObject: {
						...this.speakersLookup[speaker.code], // Use the potentially updated speakerObj
						sessions: speakerSessions.map(s => ({...s, faved: this.favs.includes(s.id)})),
						isLoading: false // Fetch attempt is done, modal's own spinner can be turned off.
										 // Content visibility (biography) depends on speakerObj.apiContent.
					}
				}
			}
		},
		async showSessionDetails(session, ev) {
			ev.preventDefault()

			// Find the talk in the schedule
			const talk = this.schedule.talks.find(t => t.code === session.id)

			// Show session immediately with loading state
			this.modalContent = {
				contentType: 'session',
				contentObject: {
					...session,
					apiContent: talk.apiContent,
					isLoading: !talk.apiContent,
					faved: this.favs.includes(session.id)
				}
			}
			this.$refs.sessionModal?.showModal()

			// Fetch additional data if needed
			if (!talk.apiContent) {
				try {
					// Ensure isLoading is true for the session description part
					if (this.modalContent && this.modalContent.contentType === 'session' && this.modalContent.contentObject.id === session.id) {
						this.modalContent.contentObject.isLoading = true;
					}
					talk.apiContent = await this.remoteApiRequest(`submissions/${session.id}/?expand=answers.question,resources`, 'GET')
					// Update content with fetched description if we are still on the same session
					if (this.modalContent && this.modalContent.contentType === 'session' && this.modalContent.contentObject.id === session.id) {
						this.modalContent = {
							contentType: 'session',
							contentObject: {
								...session,
								apiContent: talk.apiContent,
								isLoading: false,
								faved: this.favs.includes(session.id)
							}
						}
					}
				} catch (e) {
					console.error('Failed to fetch session details:', e)
					if (this.modalContent && this.modalContent.contentType === 'session' && this.modalContent.contentObject.id === session.id) {
						this.modalContent.contentObject.isLoading = false
					}
				}
			}

			// Asynchronously fetch speaker biographies for all speakers in this session
			if (session.speakers && session.speakers.length > 0) {
				const speakerFetchPromises = session.speakers.map(spk =>
					this.fetchSpeakerApiContentIfNeeded(spk.code)
				);
				// We don't need to await these here; they will update speaker objects reactively.
				// Errors are logged by the helper.
				Promise.allSettled(speakerFetchPromises);
			}
		},
		jumpToNow () {
			if (this.$refs.gridScheduleWrapper && this.$refs.gridScheduleWrapper.scrollToNow) {
				this.$refs.gridScheduleWrapper.scrollToNow()
			}
			if (this.$refs.linearSchedule && this.$refs.linearSchedule.scrollToNow) {
				this.$refs.linearSchedule.scrollToNow()
			}
			this.jumpToNowDismissed = true
		},
		dismissJumpToNow () {
			this.jumpToNowDismissed = true
		},
		onTrackToggled (trackId) {
			if (this.selectedTrackIds.includes(trackId)) {
				this.selectedTrackIds = this.selectedTrackIds.filter(id => id !== trackId)
			} else {
				this.selectedTrackIds.push(trackId)
			}
		},
		onLanguageToggled (languageCode) {
			if (this.selectedLanguageCodes.includes(languageCode)) {
				this.selectedLanguageCodes = this.selectedLanguageCodes.filter(code => code !== languageCode)
			} else {
				this.selectedLanguageCodes.push(languageCode)
			}
		},
		onTagToggled (tagId) {
			if (this.selectedTagIds.includes(tagId)) {
				this.selectedTagIds = this.selectedTagIds.filter(id => id !== tagId)
			} else {
				this.selectedTagIds.push(tagId)
			}
		},
		onSearchQueryChange (query) {
			this.searchQuery = query
		},
		onDoNotRecordToggled () {
			this.filterDoNotRecord = !this.filterDoNotRecord
		},
		clearAllFilters () {
			this.selectedTrackIds = []
			this.selectedLanguageCodes = []
			this.selectedTagIds = []
			this.filterDoNotRecord = false
			this.searchQuery = ''
			this.onlyFavs = false
		},
		toggleFavs () {
			this.onlyFavs = !this.onlyFavs
		},
		async checkForScheduleUpdate () {
			if (!this.schedule || !this.remoteApiUrl) return

			try {
				const response = await fetch(`${this.remoteApiUrl}schedules/by-version/?latest=1`, {
					credentials: this.onHomeServer ? 'same-origin' : 'omit'
				})

				if (response.ok) {
					const latestUrl = await response.text()

					if (latestUrl.trim()) {
						const expectedPath = `/schedules/${this.schedule.schedule_id}/`

						if (!latestUrl.endsWith(expectedPath)) {
							console.log(`New schedule version detected, URL: ${latestUrl}`)
							await this.refetchSchedule()
						}
					}
				}
			} catch (error) { }
		},
		async refetchSchedule () {
			try {
				const newSchedule = await fetchSchedule(this.eventUrl, this.version)

				if (!newSchedule.talks.length) {
					console.error('Refetched schedule has no talks')
					return
				}

				this.schedule = newSchedule

				this.selectedTrackIds = this.selectedTrackIds.filter(id =>
					this.schedule.tracks.some(t => t.id === id)
				)
				this.selectedLanguageCodes = this.selectedLanguageCodes.filter(code =>
					this.availableLanguages.includes(code)
				)
				this.selectedTagIds = this.selectedTagIds.filter(id =>
					this.availableTags.some(t => t.id === id)
				)
				this.favs = this.pruneFavs(this.favs, this.schedule)

				console.log(`Schedule updated to version ${this.schedule.version || 'unknown'}`)
			} catch (error) {
				console.error('Failed to refetch schedule:', error)
			}
		}
	}
}
</script>
<style lang="stylus">
@import 'styles/global.styl'
.schedule-notice
	font-size: 18px
	text-align: center
	padding: 32px
	&.error
		color: $clr-error
	&.info
		color: $clr-grey-600
	&.filtered-empty
		color: $clr-grey-600
		padding-top: 48px
		.clear-filters-button
			margin-top: 16px
			padding: 10px 20px
			background-color: var(--pretalx-clr-primary)
			color: white
			border: none
			border-radius: 6px
			font-size: 14px
			font-weight: 500
			cursor: pointer
			&:hover
				opacity: 0.9
	.notice-message
		margin-top: 16px

.pretalx-schedule, dialog.pretalx-modal
	color: rgb(13 15 16)

.pretalx-schedule
	display: flex
	flex-direction: column
	min-height: 0
	height: 100%
	font-size: 14px
	background-color: $clr-grey-50
	--pretalx-clr-text: rgb(13,15,16)
	&.grid-schedule
		min-width: min-content
		max-width: var(--schedule-max-width)
		margin: 0 auto
	&.list-schedule
		min-width: 0
	.days-wrapper
		background-color: $clr-white
		width: 100%
		position: sticky
		top: var(--pretalx-sticky-top-offset, 0px)
		z-index: 30
	.days
		background-color: $clr-white
		tabs-style(active-color: var(--pretalx-clr-primary), indicator-color: var(--pretalx-clr-primary), background-color: transparent)
		overflow-x: auto
		left: 0
		margin: 0 auto
		flex: none
		min-width: 0
		max-width: var(--schedule-max-width)
		height: 48px
		.bunt-tabs-header
			min-width: min-content
		.bunt-tabs-header-items
			justify-content: center
			min-width: min-content
			.bunt-tab-header-item
				min-width: min-content
			.bunt-tab-header-item-text
				white-space: nowrap
.error-messages
	position: fixed
	width: 250px
	bottom: 0
	right: 0
	padding: 12px
	z-index: 1000
	.error-message
		padding: 8px
		color: $clr-danger
		background-color: $clr-white
		border: 2px solid $clr-danger
		border-radius: 6px
		box-shadow: 0 2px 4px rgba(0,0,0,0.2)
		margin-top: 8px
		position: relative
		.btn
			border: 1px solid $clr-danger
			border-radius: 2px
			box-shadow: 1px 1px 2px rgba(0,0,0,0.2)
			width: 18px
			height: 18px
			position: absolute
			top: 4px
			right: 4px
			display: flex
			justify-content: center
			align-items: center
			cursor: pointer
		.message
			margin-right: 22px
.powered-by
	text-align: center
	color: $clr-grey-600
	font-size: 12px
	margin-top: 16px
	margin-bottom: 16px
	.pretalx
		transition: all 0.1s ease-in
		font-weight: bold
		margin-left: 4px
		color: $clr-grey-600
	&:hover .pretalx
		color: #3aa57c

</style>
