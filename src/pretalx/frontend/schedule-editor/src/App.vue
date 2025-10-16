<!--
SPDX-FileCopyrightText: 2022-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
.pretalx-schedule(:style="{'--scrollparent-width': scrollParentWidth + 'px'}", :class="[draggedSession ? 'is-dragging' : '', displayMode === 'condensed' ? 'condensed-mode' : 'expanded-mode']", @pointerup="stopDragging")
	template(v-if="schedule")
		.schedule-header.no-print
			.schedule-controls-left
				button.mode-toggle-button(@click="toggleDisplayMode", :class="{'active': displayMode === 'condensed'}")
					i.fa(:class="displayMode === 'condensed' ? 'fa-expand' : 'fa-compress'")
					span.mode-label {{ displayMode === 'condensed' ? $t('Expanded View') : $t('Condensed View') }}
			#schedule-action-wrapper-target
		#main-wrapper
			#unassigned.no-print(v-scrollbar.y="", @pointerenter="isUnassigning = true", @pointerleave="isUnassigning = false", :class="{'pinned': unassignedPanelPinned, 'collapse-container': displayMode === 'condensed'}")
				template(v-if="displayMode === 'condensed'")
					h4
						span {{ $t('Unscheduled sessions') }} ({{ unscheduled.length }})
						.controls
							.pin-button(@click.stop="pinUnassignedPanel", :class="{'pinned': unassignedPanelPinned}")
								i.fa.fa-thumb-tack
				template(v-else)
					.title
						bunt-input#filter-input(v-model="unassignedFilterString", :placeholder="translations.filterSessions", icon="search")
						#unassigned-sort(@click="showUnassignedSortMenu = !showUnassignedSortMenu", :class="{'active': showUnassignedSortMenu}")
							i.fa.fa-sort
					#unassigned-sort-menu(v-if="showUnassignedSortMenu")
						.sort-method(v-for="method of unassignedSortMethods", @click="unassignedSort === method.name ? unassignedSortDirection = unassignedSortDirection * -1 : unassignedSort = method.name; showUnassignedSortMenu = false")
							span {{ method.label }}
							i.fa.fa-sort-amount-asc(v-if="unassignedSort === method.name && unassignedSortDirection === 1")
							i.fa.fa-sort-amount-desc(v-if="unassignedSort === method.name && unassignedSortDirection === -1")
				.session-list(:class="{'collapse-content': displayMode === 'condensed'}")
					session.new-break(:session="{title: '+ ' + translations.newBreak}", :isDragged="false", :displayMode="displayMode", @startDragging="startNewBreak", @click="showNewBreakHint", v-tooltip.fixed="{text: newBreakTooltip, show: newBreakTooltip}", @pointerleave="removeNewBreakHint")
					session(v-for="un in unscheduled", :session="un", :displayMode="displayMode", @startDragging="startDragging", :isDragged="draggedSession && un.id === draggedSession.id", @click="editorStart(un)")
			#schedule-wrapper(v-scrollbar.x.y="")
				.schedule-controls
					bunt-tabs.days(v-if="days", :modelValue="currentDay.format()", ref="tabs" :class="['grid-tabs']")
						bunt-tab(v-for="day of days", :id="day.format()", :header="day.format(dateFormat)", @selected="changeDay(day)")
				grid-schedule(:sessions="sessions",
					:rooms="schedule.rooms",
					:availabilities="availabilities",
					:warnings="warnings",
					:start="days[0]",
					:end="days.at(-1).clone().endOf('day')",
					:currentDay="currentDay",
					:draggedSession="draggedSession",
					:displayMode="displayMode",
					@changeDay="currentDay = $event",
					@startDragging="startDragging",
					@rescheduleSession="rescheduleSession",
					@createSession="createSession",
					@editSession="editorStart($event)")
			#session-editor-wrapper(v-if="editorSession", @click="editorSession = null")
				form#session-editor(@click.stop="", @submit.prevent="editorSave")
					h3.session-editor-title
						a(v-if="editorSession.code", :href="`/orga/event/${eventSlug}/submissions/${editorSession.code}/`") {{editorSession.title }}
						span(v-else-if="editorSession.title") {{getLocalizedString(editorSession.title) }}
						.btn-sm.btn-secondary.close-button(@click="editorSession = null", role="button")
							i.fa.fa-times
					.data
						template(v-if="editorSession.code && editorSession.speakers && editorSession.speakers.length > 0")
							.data-row.form-group.row
								label.data-label.col-form-label.col-md-3 {{ $t('Speakers') }}
								.col-md-9.data-value
									span(v-for="speaker, index of editorSession.speakers")
										a(:href="`/orga/event/${eventSlug}/speakers/${speaker.code}/`") {{speaker.name}}
										span(v-if="index != editorSession.speakers.length - 1") {{', '}}
							.data-row.form-group.row
								label.data-label.col-form-label.col-md-3 {{ $t('Availabilities') }}
								.col-md-9.data-value
									ul.mt-0.mb-0
										li(v-for="availability of editorSessionAvailabilities") {{ availability }}
						.data-row(v-else).form-group.row
							label.data-label.col-form-label.col-md-3 {{ $t('Title') }}
							.col-md-9
								.i18n-form-group
									template(v-for="locale of locales")
										input(v-model="editorSession.title[locale]", :required="true", :lang="locale", type="text")
						.data-row(v-if="editorSession.track").form-group.row
							label.data-label.col-form-label.col-md-3 {{ $t('Track') }}
							.col-md-9.data-value {{ getLocalizedString(editorSession.track.name) }}
						.data-row(v-if="editorSession.room").form-group.row
							label.data-label.col-form-label.col-md-3 {{ $t('Room') }}
							.col-md-9.data-value {{ getLocalizedString(editorSession.room.name) }}
						.data-row.form-control.form-group.row
							label.data-label.col-form-label.col-md-3 {{ $t('Duration') }}
							.col-md-9.number.input-group
								input(v-model="editorSession.duration", type="number", min="1", max="1440", step="1", :required="true")
								.input-group-append
									span.input-group-text {{ $t('minutes') }}

						.data-row(v-if="editorSession.code && warnings[editorSession.code] && warnings[editorSession.code].length").form-group.row
							label.data-label.col-form-label.col-md-3
								i.fa.fa-exclamation-triangle.warning
								span {{ $t('Warnings') }}
							.col-md-9.data-value
								ul(v-if="warnings[editorSession.code].length > 1")
									li.warning(v-for="warning of warnings[editorSession.code]") {{ warning.message }}
								span(v-else) {{ warnings[editorSession.code][0].message }}
					.button-row
						input(type="submit")
						bunt-button.mr-1#btn-delete(v-if="!editorSession.code", @click="editorDelete", :loading="editorSessionWaiting") {{ $t('Delete') }}
						bunt-button.mr-1#btn-unschedule(v-if="editorSession.start && editorSession.room && editorSession.code", @click="editorUnschedule", :loading="editorSessionWaiting") {{ $t('Unschedule') }}
						bunt-button.mr-1#btn-copy-to-rooms(v-if="!editorSession.code && editorSession.start && editorSession.room && editorAvailableRoomsForCopy.length > 0", @click="editorCopyToOtherRooms", :loading="editorSessionWaiting") {{ $t('Copy to other rooms') }}
						bunt-button#btn-save(@click="editorSave", :loading="editorSessionWaiting") {{ $t('Save') }}
	bunt-progress-circular(v-else, size="huge", :page="true")
</template>
<script>
import moment from 'moment-timezone'
import Editor from '~/components/Editor'
import GridSchedule from '~/components/GridSchedule'
import Session from '~/components/Session'
import api from '~/api'
import { getLocalizedString } from '~/utils'

export default {
	name: 'PretalxSchedule',
	components: { Editor, GridSchedule, Session },
	props: {
		locale: String,
		version: {
			type: String,
			default: ''
		}
	},
	data () {
		return {
			moment,
			eventSlug: null,
			scrollParentWidth: Infinity,
			schedule: null,
			availabilities: {rooms: {}, talks: {}},
			warnings: {},
			currentDay: null,
			draggedSession: null,
			editorSession: null,
			editorSessionWaiting: false,
			isUnassigning: false,
			locales: ["en"],
			unassignedFilterString: '',
			unassignedSort: 'title',
			unassignedSortDirection: 1,  // asc
			showUnassignedSortMenu: false,
			newBreakTooltip: '',
			displayMode: localStorage.getItem('scheduleDisplayMode') || 'expanded',
			unassignedPanelPinned: false,
			getLocalizedString,
			// i18next-parser doesn't have a pug parser / fails to parse translated
			// strings in attributes (though plain {{}} strings work!), so anything
			// handled in attributes will be collected here instead
			translations: {
				filterSessions: this.$t('Filter sessions'),
				newBreak: this.$t('New break'),
			}
		}
	},
	computed: {
		roomsLookup () {
			if (!this.schedule) return {}
			return this.schedule.rooms.reduce((acc, room) => { acc[room.id] = room; return acc }, {})
		},
		editorAvailableRoomsForCopy () {
			// Check if we can copy the current break to other rooms
			if (!this.editorSession || this.editorSession.code || !this.editorSession.start || !this.editorSession.room) {
				return []
			}
			// Find all rooms that are free at the break's time
			const breakStart = moment(this.editorSession.start)
			const breakEnd = moment(this.editorSession.end || breakStart.clone().add(this.editorSession.duration, 'minutes'))
			const availableRooms = []

			for (const room of this.schedule.rooms) {
				if (room.id === this.editorSession.room.id || room.id === this.editorSession.room) {
					// Skip the current room
					continue
				}
				// Check if there's any session overlapping with the break time in this room
				const hasOverlap = this.schedule.talks.some(talk => {
					if (!talk.start || !talk.room) return false
					if ((talk.room.id || talk.room) !== room.id) return false
					const talkStart = moment(talk.start)
					const talkEnd = moment(talk.end)
					// Check for time overlap
					return talkStart.isBefore(breakEnd) && talkEnd.isAfter(breakStart)
				})
				if (!hasOverlap) {
					availableRooms.push(room)
				}
			}
			return availableRooms
		},
		tracksLookup () {
			if (!this.schedule) return {}
			return this.schedule.tracks.reduce((acc, t) => { acc[t.id] = t; return acc }, {})
		},
		editorSessionAvailabilities () {
			if (!this.editorSession) return []
			const avails = this.availabilities.talks[this.editorSession.id]
			if (!avails.length) return ["–"]
			return avails.map(a => {
				const start = moment(a.start)
				const end = moment(a.end)
				if (start.isSame(end, 'day')) {
					return `${start.format('L LT')} - ${end.format('LT')}`
				} else {
					return `${start.format('L LT')} - ${end.format('L LT')}`
				}
			})
		},
		unassignedSortMethods () {
			const sortMethods = [
				{label: this.$t('Title'), name: 'title'},
				{label: this.$t('Speakers'), name: 'speakers'},
			]
			if (this.schedule && this.schedule.tracks.length > 1) {
				sortMethods.push({label: this.$t('Track'), name: 'track'})
			}
			sortMethods.push({label: this.$t('Duration'), name: 'duration' })
			return sortMethods
		},
		speakersLookup () {
			if (!this.schedule) return {}
			return this.schedule.speakers.reduce((acc, s) => { acc[s.code] = s; return acc }, {})
		},
		unscheduled () {
			if (!this.schedule) return
			let sessions = []
			for (const session of this.schedule.talks.filter(s => !s.start || !s.room)) {
				sessions.push({
					id: session.id,
					code: session.code,
					title: session.title,
					abstract: session.abstract,
					speakers: session.speakers?.map(s => this.speakersLookup[s]),
					track: this.tracksLookup[session.track],
					duration: session.duration,
					state: session.state,
				})
			}
			if (this.unassignedFilterString.length) {
				sessions = sessions.filter(s => {
					const title = getLocalizedString(s.title)
					const speakers = s.speakers?.map(s => s.name).join(', ') || ''
					return title.toLowerCase().includes(this.unassignedFilterString.toLowerCase()) || speakers.toLowerCase().includes(this.unassignedFilterString.toLowerCase())
				})
			}
			// Sort by this.unassignedSort, this.unassignedSortDirection (1 or -1)
			sessions = sessions.sort((a, b) => {
				if (this.unassignedSort == 'title') {
					return getLocalizedString(a.title).toUpperCase().localeCompare(getLocalizedString(b.title).toUpperCase()) * this.unassignedSortDirection
				} else if (this.unassignedSort == 'speakers') {
					const aSpeakers = a.speakers?.map(s => s.name).join(', ') || ''
					const bSpeakers = b.speakers?.map(s => s.name).join(', ') || ''
					return aSpeakers.toUpperCase().localeCompare(bSpeakers.toUpperCase()) * this.unassignedSortDirection
				} else if (this.unassignedSort == 'track') {
					return getLocalizedString(a.track ? a.track.name : '').toUpperCase().localeCompare(getLocalizedString(b.track? b.track.name : '').toUpperCase()) * this.unassignedSortDirection
				} else if (this.unassignedSort == 'duration') {
					return (a.duration - b.duration) * this.unassignedSortDirection
				}
			})
			return sessions
		},
		sessions () {
			if (!this.schedule) return
			const sessions = []
			for (const session of this.schedule.talks.filter(s => s.start && moment(s.start).isSameOrAfter(this.days[0]) && moment(s.start).isSameOrBefore(this.days.at(-1).clone().endOf('day')))) {
				sessions.push({
					id: session.id,
					code: session.code,
					title: session.title,
					abstract: session.abstract,
					start: moment(session.start),
					end: moment(session.end),
					duration: moment(session.end).diff(session.start, 'm'),
					speakers: session.speakers?.map(s => this.speakersLookup[s]),
					track: this.tracksLookup[session.track],
					state: session.state,
					room: this.roomsLookup[session.room]
				})
			}
			sessions.sort((a, b) => a.start.diff(b.start))
			return sessions
		},
		days () {
			if (!this.schedule) return
			const days = [moment(this.schedule.event_start).startOf('day')]
			const lastDay = moment(this.schedule.event_end)
			while (!days.at(-1).isSame(lastDay, 'day')) {
				days.push(days.at(-1).clone().add(1, 'days'))
			}
			return days
		},
		inEventTimezone () {
			if (!this.schedule || !this.schedule.talks) return false
			const example = this.schedule.talks[0].start
			return moment.tz(example, this.userTimezone).format('Z') === moment.tz(example, this.schedule.timezone).format('Z')
		},
		dateFormat () {
			// Defaults to dddd DD. MMMM for: all grid schedules with more than two rooms, and all list schedules with less than five days
			// After that, we start to shorten the date string, hoping to reduce unwanted scroll behaviour
			if ((this.schedule && this.schedule.rooms.length > 2) || !this.days || !this.days.length) return 'dddd DD. MMMM'
			if (this.days && this.days.length <= 5) return 'dddd DD. MMMM'
			if (this.days && this.days.length <= 7) return 'dddd DD. MMM'
			return 'ddd DD. MMM'
		}
	},
	async created () {
		const version = ''
		this.schedule = await this.fetchSchedule()
		// needs to be as early as possible
		this.eventTimezone = this.schedule.timezone
		moment.tz.setDefault(this.eventTimezone)
		this.locales = this.schedule.locales
		this.eventSlug = window.location.pathname.split("/")[3]
		this.currentDay = this.days[0]
		window.setTimeout(this.pollUpdates, 10 * 1000)
		await this.fetchAdditionalScheduleData()
		await new Promise((resolve) => {
			const poll = () => {
				if (this.$el.parentElement || this.$el.getRootNode().host) return resolve()
				setTimeout(poll, 100)
			}
			poll()
		})
	},
	async mounted () {
		// We block until we have either a regular parent or a shadow DOM parent
		window.addEventListener('resize', this.onWindowResize)
		this.onWindowResize()

		// Move the Django-generated action buttons into the Vue header with retry
		const moveActionButtons = () => {
			const actionWrapper = document.getElementById('schedule-action-wrapper')
			const actionTarget = document.getElementById('schedule-action-wrapper-target')
			if (actionWrapper && actionTarget) {
				actionTarget.appendChild(actionWrapper)
				actionWrapper.style.display = 'flex'
				return true
			}
			return false
		}

		// Retry up to 50 times with 100ms delay (5 seconds total)
		let attempts = 0
		const maxAttempts = 50
		const tryMove = () => {
			if (moveActionButtons()) {
				return
			}
			attempts++
			if (attempts < maxAttempts) {
				setTimeout(tryMove, 100)
			}
		}
		this.$nextTick(tryMove)
	},
	destroyed () {
		// TODO destroy observers
	},
	methods: {
		toggleDisplayMode () {
			const newMode = this.displayMode === 'expanded' ? 'condensed' : 'expanded'
			this.displayMode = newMode
			localStorage.setItem('scheduleDisplayMode', newMode)

			// Handle sidebar collapse/expand
			if (newMode === 'condensed') {
				// Collapse sidebar in condensed mode
				const sidebar = document.querySelector('.sidebar')
				if (sidebar && !sidebar.classList.contains('collapsed')) {
					localStorage.removeItem('sidebarVisible')
					document.documentElement.classList.remove('sidebar-expanded')
				}
				// Reset unassigned panel to unpinned
				this.unassignedPanelPinned = false
			}
		},
		pinUnassignedPanel () {
			this.unassignedPanelPinned = !this.unassignedPanelPinned
		},
		changeDay (day) {
			if (day.isSame(this.currentDay)) return
			this.currentDay = moment(day, this.eventTimezone).startOf('day')
			window.location.hash = day.format('YYYY-MM-DD')
		},
		saveTalk (session) {
			api.saveTalk(session).then(response => {
				this.warnings[session.code] = response.warnings
				this.schedule.talks.find(s => s.id === session.id).updated = response.updated
			})
		},
		rescheduleSession (e) {
			const movedSession = this.schedule.talks.find(s => s.id === e.session.id)
			this.stopDragging()
			movedSession.start = e.start
			movedSession.end = e.end
			movedSession.room = e.room.id
			this.saveTalk(movedSession)
		},
		createSession (e) {
			api.createTalk(e.session).then(response => {
				this.warnings[e.session.code] = response.warnings
				const newSession = Object.assign({}, e.session)
				newSession.id = response.id
				this.schedule.talks.push(newSession)
				this.editorStart(newSession)
			})
		},
		editorStart (session) {
			this.editorSession = session
		},
		editorSave () {
			this.editorSessionWaiting = true
			this.editorSession.end = moment(this.editorSession.start).clone().add(this.editorSession.duration, 'm')
			this.saveTalk(this.editorSession)

			const session = this.schedule.talks.find(s => s.id === this.editorSession.id)
			session.end = this.editorSession.end
			if (!session.submission) {
				session.title = this.editorSession.title
			}
			this.editorSessionWaiting = false
			this.editorSession = null
		},
		editorDelete () {
			this.editorSessionWaiting = true
			api.deleteTalk(this.editorSession)
			this.schedule.talks = this.schedule.talks.filter(s => s.id !== this.editorSession.id)
			this.editorSessionWaiting = false
			this.editorSession = null
		},
		editorUnschedule () {
			this.editorSessionWaiting = true
			const session = this.schedule.talks.find(s => s.id === this.editorSession.id)
			session.start = null
			session.end = null
			session.room = null
			this.editorSession.start = null
			this.editorSession.end = null
			this.editorSession.room = null
			this.saveTalk(session)
			this.editorSessionWaiting = false
			this.editorSession = null
		},
		async editorCopyToOtherRooms () {
			// Copy the current break to all available rooms
			this.editorSessionWaiting = true
			const availableRooms = this.editorAvailableRoomsForCopy

			for (const room of availableRooms) {
				const newBreak = {
					title: this.editorSession.title,
					description: this.editorSession.description,
					start: this.editorSession.start,
					end: this.editorSession.end,
					duration: this.editorSession.duration,
					room: room.id
				}

				try {
					const response = await api.createTalk(newBreak)
					// Add the newly created break to the schedule
					const createdBreak = {
						id: response.id,
						title: newBreak.title,
						description: newBreak.description,
						start: newBreak.start,
						end: newBreak.end,
						duration: newBreak.duration,
						room: room.id
					}
					this.schedule.talks.push(createdBreak)
					if (response.warnings) {
						this.warnings[response.id] = response.warnings
					}
				} catch (error) {
					console.error('Failed to create break in room', room, error)
				}
			}

			this.editorSessionWaiting = false
			this.editorSession = null
		},
		showNewBreakHint () {
			// Users try to click the "+ New Break" box instead of dragging it to the schedule
			// so we show a hint on-click
			this.newBreakTooltip = this.$t('Drag the box to the schedule to create a new break')
		},
		removeNewBreakHint () {
			this.newBreakTooltip = ''
		},
		startNewBreak({event}) {
			const title = this.locales.reduce((obj, locale) => {
				obj[locale] = this.$t("New break")
				return obj
			}, {})
			this.startDragging({event, session: {title, duration: "5", uncreated: true}})
		},
		startDragging ({event, session}) {
			if (this.availabilities && this.availabilities.talks[session.id] && this.availabilities.talks[session.id].length !== 0) {
				session.availabilities = this.availabilities.talks[session.id]
			}
			// TODO: capture the pointer with setPointerCapture(event)
			// This allows us to call stopDragging() even when the mouse is released
			// outside the browser.
			// https://developer.mozilla.org/en-US/docs/Web/API/Element/setPointerCapture
			this.draggedSession = session
		},
		stopDragging (session) {
			try {
				if (this.isUnassigning && this.draggedSession) {
					if (this.draggedSession.code) {
						const movedSession = this.schedule.talks.find(s => s.id === this.draggedSession.id)
						movedSession.start = null
						movedSession.end = null
						movedSession.room = null
						this.saveTalk(movedSession)
					} else if (this.schedule.talks.find(s => s.id === this.draggedSession.id)) {
						this.schedule.talks = this.schedule.talks.filter(s => s.id !== this.draggedSession.id)
						api.deleteTalk(this.draggedSession)
					}
				}
			} finally {
				this.draggedSession = null
				this.isUnassigning = false
			}
		},
		onWindowResize () {
			this.scrollParentWidth = document.body.offsetWidth
		},
		async fetchSchedule(options) {
		  const schedule = await (api.fetchTalks(options))
		  return schedule
		},
		async fetchAdditionalScheduleData() {
			this.availabilities = await api.fetchAvailabilities()
			this.warnings = await api.fetchWarnings()
		},
		async pollUpdates () {
			this.fetchSchedule({since: this.since, warnings: true}).then(schedule => {
				if (schedule.version !== this.schedule.version) {
					// we need to reload if a new schedule version is available
					window.location.reload()
				}
				// For each talk in the schedule, we check if it has changed and if our update date is newer than the last change
				schedule.talks.forEach(talk => {
					const oldTalk = this.schedule.talks.find(t => t.id === talk.id)
					if (!oldTalk) {
						this.schedule.talks.push(talk)
					} else {
						if (moment(talk.updated).isAfter(moment(oldTalk.updated))) {
							Object.assign(oldTalk, talk)
						}
					}
				})
				this.since = schedule.now
				window.setTimeout(this.pollUpdates, 10 * 1000)
			})
		}
	}
}
</script>
<style lang="stylus">
#page-content
	padding: 0
.pretalx-schedule
	display: flex
	flex-direction: column
	min-height: 0
	min-width: 0
	height: calc(100vh - 85px)
	width: 100%
	font-size: 14px
	padding-left: 24px
	font-family: var(--font-family)
	color: var(--color-text)
	h1, h2, h3, h4, h5, h6, legend, button, .btn
		font-family: var(--font-family-title)
	.bunt-scrollbar-rail-wrapper-y
		display: none
	&.is-dragging
		user-select: none
		cursor: grabbing
	#main-wrapper
		display: flex
		flex: auto
		min-height: 0
		min-width: 0
	.collapse-container
		position: fixed
		bottom: 0
		right: 0
		width: 300px
		z-index: 500
		background-color: $clr-white
		padding: 8px 16px
		box-shadow: 0 0 10px rgba(0, 0, 0, 0.3)
		border-top-left-radius: 8px
		overflow-y: hidden
		.collapse-content
			display: none
			overflow-y: auto
		&:hover
			.collapse-content
				display: block
		h4
			margin: 0
			font-size: 16px
			display: flex
			justify-content: space-between
			align-items: center
	&.condensed-mode
		#unassigned
			margin-top: 0
			z-index: 501
			font-size: 16px
			.session-list
				margin-right: 0
			&.pinned .collapse-content
				display: block
			.bunt-scrollbar-rail-wrapper-y
				top: 30px
			.pin-button
				padding: 0
				cursor: pointer
				&:hover
					opacity: 0.7
				&.pinned
					color: var(--color-primary)
			.session-list
				max-height: 400px
		#schedule-wrapper
			margin-right: 0
	.settings
		margin-left: 18px
		align-self: flex-start
		display: flex
		align-items: center
		position: sticky
		z-index: 100
		left: 18px
		.bunt-select
			max-width: 300px
			padding-right: 8px
		.timezone-label
			cursor: default
			color: $clr-secondary-text-light
	.days
		tabs-style(active-color: var(--color-primary), indicator-color: var(--color-primary), background-color: transparent)
		overflow-x: auto
		margin-bottom: 0
		flex: auto
		min-width: 0
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
	#unassigned
		margin-top: 35px
		background-color: $clr-white
		width: 350px
		flex: none
		.session-list
			margin-right: 12px
		> .bunt-scrollbar-rail-y
			margin: 0
		> .title
			padding 4px 0
			font-size: 18px
			text-align: center
			background-color: $clr-white
			border-bottom: 4px solid $clr-dividers-light
			display: flex
			align-items: flex-end
			margin-left: 8px
			#filter-input
				width: calc(100% - 36px)
				.label-input-container, .label-input-container:active
					.outline
						display: none
			#unassigned-sort
				width: 28px
				height: 28px
				text-align: center
				cursor: pointer
				border-radius: 4px
				margin-bottom: 8px
				margin-left: 4px
				color: $clr-secondary-text-light
				&:hover, &.active
					opacity: 0.8
					background-color: $clr-dividers-light
		.new-break.c-linear-schedule-session
			min-height: 48px
		#unassigned-sort-menu
			color: $clr-primary-text-light
			display: flex
			flex-direction: column
			background-color: white
			position: absolute
			top: 53px
			right: 15px
			width: 130px
			font-size: 16px
			cursor: pointer
			z-index: 1000
			box-shadow: 0 2px 4px rgba(0, 0, 0, 0.5)
			text-align: left;
			.sort-method
				padding: 8px 16px
				display: flex
				justify-content: space-between
				align-items: center
				&:hover
					background-color: $clr-dividers-light
	.schedule-header
		display: flex
		justify-content: space-between
		align-items: center
		margin: 1rem 42px 1rem 8px
		max-width: 100%
		padding: 0
		.schedule-controls-left
			display: flex
			align-items: center
			gap: 12px
			.mode-toggle-button
				display: flex
				align-items: center
				gap: 8px
				padding: 8px 16px
				background-color: $clr-white
				border: 1px solid $clr-dividers-light
				border-radius: 4px
				cursor: pointer
				font-size: 14px
				color: $clr-primary-text-light
				transition: all 0.2s
				&:hover
					background-color: $clr-grey-100
					border-color: var(--color-primary)
				&.active
					background-color: var(--color-primary)
					color: $clr-white
					border-color: var(--color-primary)
				.fa
					font-size: 16px
		#schedule-action-wrapper-target
			display: flex
			align-items: center
			#schedule-action-wrapper
				display: flex !important
	#schedule-wrapper
		width: 100%
		margin-right: 40px
	.schedule-controls
		display: flex
		justify-content: space-between
		align-items: center
		position: sticky
		left: 0
		top: 0
		z-index: 30
		background-color: $clr-white
  #session-editor-wrapper
		position: absolute
		z-index: 1000
		top: 0
		left: 0
		width: 100%
		height: 100%
		background-color: rgba(0, 0, 0, 0.5)

		#session-editor
			background-color: $clr-white
			border-radius: 4px
			padding: 32px 40px
			position: absolute
			top: 50%
			left: 50%
			transform: translate(-50%, -50%)
			width: 680px

			.session-editor-title
				font-size: 22px
				margin-bottom: 16px
				position: relative
				.close-button
					position: absolute
					right: 0
					top: 0
			.button-row
				display: flex
				width: 100%
				margin-top: 24px

				.bunt-button-content
					font-size: 16px !important
				#btn-delete
					button-style(color: $clr-danger, text-color: $clr-white)
					font-weight: bold;
				#btn-unschedule
					button-style(color: $clr-warning, text-color: $clr-white)
					font-weight: bold;
				#btn-copy-to-rooms
					button-style(color: #4a90e2, text-color: $clr-white)
					font-weight: bold;
				#btn-save
					margin-left: auto
					font-weight: bold;
					button-style(color: #3aa57c)
				[type=submit]
					display: none
			.data
				display: flex
				flex-direction: column
				font-size: 16px
				.data-row
					.data-value
						padding-top: 8px
						ul
							list-style: none
							padding: 0
		.warning
			color: #b23e65
</style>
