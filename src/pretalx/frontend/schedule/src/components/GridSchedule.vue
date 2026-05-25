<!--
SPDX-FileCopyrightText: 2020-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
.c-grid-schedule()
	.grid(:style="gridStyle")
		template(v-for="slice of visibleTimeslices")
			.timeslice(:ref="slice.name", :class="getSliceClasses(slice)", :data-slice="slice.date.toISO()", :style="getSliceStyle(slice)") {{ getSliceLabel(slice) }}
			.timeline(:class="getSliceClasses(slice)", :style="getSliceStyle(slice)")
		.now(v-if="nowSlice", ref="now", :class="{'on-daybreak': nowSlice.onDaybreak}", :style="{'grid-area': `${nowSlice.slice.name} / 1 / auto / auto`, '--offset': nowSlice.offset}")
			svg(viewBox="0 0 10 10")
				path(d="M 0 0 L 10 5 L 0 10 z")
		.room(:style="{'grid-area': `1 / 1 / auto / auto`}")
		.room(v-for="(room, index) of rooms", :style="{'grid-area': `1 / ${index + 2 } / auto / auto`}") {{ getLocalizedString(room.name) }}
			bunt-button.room-description(v-if="getLocalizedString(room.description)", :tooltip="getLocalizedString(room.description)", tooltip-placement="bottom-end") ?
		.room(v-if="hasSessionsWithoutRoom", :style="{'grid-area': `1 / ${rooms.length + 2} / auto / -1`}") {{ translationMessages.no_location || 'No location' }}
		template(v-for="session of sessions")
			session(
				v-if="isProperSession(session)",
				:session="session",
				:now="now",
				:locale="locale",
				:timezone="timezone",
				:style="getSessionStyle(session)",
				:showAbstract="false", :showRoom="false",
				:faved="favs.includes(session.id)",
				:signedUp="signups.includes(session.id)",
				:hasAmPm="hasAmPm",
				:onHomeServer="onHomeServer",
				@fav="$emit('fav', session.id)",
				@unfav="$emit('unfav', session.id)"
			)
			.break(v-else, :style="getSessionStyle(session)")
				.time-box
					.start(v-if="hasAmPm", class="has-ampm")
						.time {{ timeWithoutAmPm(session.start.setZone(timezone), locale) }}
						.ampm {{ timeAmPm(session.start.setZone(timezone), locale) }}
					.start(v-else)
						.time {{ session.start.setZone(timezone).toLocaleString({hour: 'numeric', minute: 'numeric'}) }}
					.duration {{ getPrettyDuration(session.start, session.end) }}
					.buffer
				.info
					.title {{ getLocalizedString(session.title) }}
</template>
<script>
// TODO
// - handle click on already selected day (needs some buntpapier hacking)
// - optionally only show venueless rooms
import { DateTime } from 'luxon'
import Session from './Session'
import { getPrettyDuration, timeWithoutAmPm, timeAmPm, isProperSession} from '~/utils'
import localize from '~/mixins/localize'
import scheduleScrollMixin from '~/mixins/scheduleScroll'

const getSliceName = function (date) {
	return `slice-${date.toFormat('LL-dd-HH-mm')}`
}

export default {
	components: { Session },
	mixins: [localize, scheduleScrollMixin],
	inject: {
		translationMessages: { default: () => ({}) }
	},
	props: {
		sessions: Array,
		rooms: Array,
		favs: {
			type: Array,
			default () {
				return []
			}
		},
		signups: {
			type: Array,
			default () {
				return []
			}
		},
		currentDay: String,
		now: Object,
		timezone: String,
		locale: String,
		hasAmPm: Boolean,
		scrollParent: Element,
		onHomeServer: Boolean
	},
	emits: ['fav', 'unfav', 'changeDay'],
	data () {
		return {
			getPrettyDuration,
			timeWithoutAmPm,
			timeAmPm,
			isProperSession
		}
	},
	computed: {
		hasSessionsWithoutRoom () {
			return this.sessions.some(s => !s.room)
		},
		timeslices () {
			const minimumSliceMins = 30
			const slices = []
			const slicesLookup = {}
			const timezone = this.timezone
			const pushSlice = function (date, {hasSession = false, hasBreak = false, hasStart = false, hasEnd = false} = {}) {
				const name = getSliceName(date)
				let slice = slicesLookup[name]
				if (slice) {
					slice.hasSession = slice.hasSession || hasSession
					slice.hasBreak = slice.hasBreak || hasBreak
					slice.hasStart = slice.hasStart || hasStart
					slice.hasEnd = slice.hasEnd || hasEnd
				} else {
					slice = {
						date,
						name,
						hasSession,
						hasBreak,
						hasStart,
						hasEnd,
						datebreak: date.setZone(timezone).equals(date.setZone(timezone).startOf('day'))
					}
					slices.push(slice)
					slicesLookup[name] = slice
				}
			}
			const fillHalfHours = function (start, end, {hasSession, hasBreak} = {}) {
				// fill to the nearest half hour, then each half hour, then fill to end
				let mins = end.diff(start).shiftTo('minutes').minutes
				const startingMins = minimumSliceMins - start.minute % minimumSliceMins
				// buffer slices because we need to remove hasSession from the last one
				const halfHourSlices = []
				if (startingMins) {
					halfHourSlices.push(start.plus({minutes: startingMins}))
					mins -= startingMins
				}
				const endingMins = end.minute % minimumSliceMins
				for (let i = 1; i <= mins / minimumSliceMins; i++) {
					halfHourSlices.push(start.plus({minutes: startingMins + minimumSliceMins * i}))
				}

				if (endingMins) {
					halfHourSlices.push(end.minus({'minutes': endingMins}))
				}

				// last slice is actually just after the end of the session and has no session
				const lastSlice = halfHourSlices.pop()
				halfHourSlices.forEach(slice => pushSlice(slice, {hasSession, hasBreak}))
				pushSlice(lastSlice)
			}
			for (const session of this.sessions) {
				const lastSlice = slices[slices.length - 1]
				// gap to last slice
				if (!lastSlice) {
					pushSlice(session.start.setZone(timezone).startOf('day'))
				} else if (session.start > lastSlice.date) {
					fillHalfHours(lastSlice.date, session.start)
				}

				const isProper = this.isProperSession(session)
				// add start and end slices for the session itself
				pushSlice(session.start, {hasSession: isProper, hasBreak: !isProper, hasStart: true})
				pushSlice(session.end, {hasEnd: true})
				// add half hour slices between a session
				fillHalfHours(session.start, session.end, {hasSession: isProper, hasBreak: !isProper})
			}

			const sliceIsFraction = function (slice) {
				if (!slice) return
				return slice.date.minute !== 0 && slice.date.minute !== minimumSliceMins
			}

			const sliceShouldDisplay = function (slice, index) {
				if (!slice) return
				// keep slices with sessions or when changing dates, or when sessions start or immediately after they end
				if (slice.hasSession || slice.datebreak || slice.hasStart || slice.hasEnd) return true
				const prevSlice = slices[index - 1]
				const nextSlice = slices[index + 1]

				// keep non-whole slices
				if (sliceIsFraction(slice)) return true
				// keep slices before and after non-whole slices, if by session or break
				if (
					((prevSlice?.hasSession || prevSlice?.hasBreak || prevSlice?.hasEnd) && sliceIsFraction(prevSlice)) ||
					((nextSlice?.hasSession || nextSlice?.hasBreak) && sliceIsFraction(nextSlice)) ||
					((!nextSlice?.hasSession || !nextSlice?.hasBreak) && (slice.hasSession || slice.hasBreak) && sliceIsFraction(nextSlice))
				) return true
				// but drop slices inside breaks
				if (prevSlice?.hasBreak && slice.hasBreak) return false
				return false
			}

			slices.sort((a, b) => a.date.diff(b.date))
			// remove empty gaps in slices
			const compactedSlices = []
			for (const [index, slice] of slices.entries()) {
				if (sliceShouldDisplay(slice, index)) {
					compactedSlices.push(slice)
					continue
				}
				// make the previous slice a gap slice if this one would be the first to be removed
				// but only if it isn't the start of the day
				const prevSlice = slices[index - 1]
				if (sliceShouldDisplay(prevSlice, index - 1) && !prevSlice.datebreak) {
					prevSlice.gap = true
				}
			}
			// Only count slice as gap if it is longer than 30 minutes
			compactedSlices.forEach((slice, index) => {
				if (slice.gap && index < compactedSlices.length - 1) {
					if (compactedSlices[index + 1].date.diff(slice.date).shiftTo('minutes').minutes <= 30) slice.gap = false
				}
			})
			// remove gap at the end of the schedule
			if (compactedSlices[compactedSlices.length - 1].gap) compactedSlices.pop()
			return compactedSlices
		},
		visibleTimeslices () {
			return this.timeslices.filter(slice => slice.date.minute % 30 === 0)
		},
		gridStyle () {
			let rows = '[header] 52px '
			rows += this.timeslices.map((slice, index) => {
				const next = this.timeslices[index + 1]
				let height = 60
				if (slice.gap) {
					height = 100
				} else if (slice.datebreak) {
					height = 60
				} else if (next) {
					height = Math.min(60, next.date.diff(slice.date).shiftTo('minutes').minutes * 2)
				}
				return `[${slice.name}] minmax(${height}px, auto)`
			}).join(' ')
			return {
				'--total-rooms': this.rooms.length,
				'grid-template-rows': rows
			}
		},
		nowSlice () {
			let slice
			for (const s of this.timeslices) {
				if (this.now < s.date) break
				slice = s
			}
			if (slice) {
				const nextSlice = this.timeslices[this.timeslices.indexOf(slice) + 1]
				if (!nextSlice) return null
				// is on daybreak
				if (nextSlice.date.diff(slice.date).shiftTo('minutes').minutes > 30) return {
					slice: nextSlice,
					offset: 0,
					onDaybreak: true
				}
				return {
					slice,
					offset: this.now.diff(slice.date).shiftTo('minutes').minutes / nextSlice.date.diff(slice.date).shiftTo('minutes').minutes
				}
			}
			return null
		}
	},
	async mounted () {
		this.setupIntersectionObserver()
	},
	methods: {
		scrollToNow () {
			if (!this.$refs.now) return
			const scrollTop = this.$refs.now.offsetTop + this.getOffsetTop()
			const scrollEl = this.scrollParent
			if (scrollEl) {
				scrollEl.scrollTo({ top: scrollTop, behavior: 'smooth' })
			} else {
				window.scroll({ top: scrollTop, behavior: 'smooth' })
			}
		},
		observeElements() {
			// GridSchedule-specific: observe only datebreak slices
			for (const [ref, el] of Object.entries(this.$refs)) {
				if (!ref.startsWith('slice')) continue
				const slice = this.timeslices.find(s => s.name === ref)
				if (!slice || !slice.datebreak) continue
				this.observer.observe(el[0])
			}
		},
		getSessionStyle (session) {
			const roomIndex = this.rooms.indexOf(session.room)
			return {
				'grid-row': `${getSliceName(session.start)} / ${getSliceName(session.end)}`,
				'grid-column': roomIndex > -1 ? roomIndex + 2 : null
			}
		},
		getOffsetTop () {
			return window.scrollY + this.$el.getBoundingClientRect().top - 100
		},
		getSliceClasses (slice) {
			return {
				datebreak: slice.datebreak,
				gap: slice.gap
			}
		},
		getSliceStyle (slice) {
			if (slice.datebreak) {
				let index = this.timeslices.findIndex(s => s.date.setZone(this.timezone).startOf('day') > slice.date.setZone(this.timezone).startOf('day'))
				if (index < 0) {
					index = this.timeslices.length - 1
				}
				return {'grid-area': `${slice.name} / 1 / ${this.timeslices[index].name} / auto`}
			}
			return {'grid-area': `${slice.name} / 1 / auto / auto`}
		},
		getSliceLabel (slice) {
			if (slice.datebreak) {
				const date = slice.date.setZone(this.timezone)
				return date.toLocaleString({ weekday: 'short' }) + '\n' + date.toLocaleString({ day: 'numeric', month: 'short' })
			}
			return slice.date.setZone(this.timezone).toLocaleString({ hour: 'numeric', minute: 'numeric' })
		},
		changeDay (day) {
			// Look for a datebreak slice that matches the target day
			const targetSlice = this.timeslices.find(slice => {
				if (!slice.datebreak) return false
				const sliceDay = slice.date.setZone(this.timezone).toISODate()
				return sliceDay === day
			})
			
			if (targetSlice) {
				const el = this.$refs[targetSlice.name]?.[0]
				if (el) {
					this.programmaticScrollTo(el)
				}
			}
		},
		calculateScrollTop(element) {
			return element.offsetTop + this.getOffsetTop()
		},
		onIntersect (entries) {
			// Skip if we're doing programmatic scroll to avoid interference with tab clicks
			if (this.programmaticScroll) return

			const entry = entries.sort((a, b) => b.time - a.time).find(entry => entry.isIntersecting)
			if (!entry) return

			// Parse the date with the correct timezone context
			const originalDate = DateTime.fromISO(entry.target.dataset.slice, { zone: this.timezone })
			// Preserve the calendar date when converting timezones for day boundaries
			const day = DateTime.fromObject({
				year: originalDate.year,
				month: originalDate.month,
				day: originalDate.day
			}, { zone: this.timezone })

			if (day.toISODate() !== this.currentDay) {
				this.$emit('changeDay', day)
			}
		},
	}
}
</script>
<style lang="stylus">
.c-grid-schedule
	flex: auto
	.grid
		display: grid
		grid-template-columns: 78px repeat(var(--total-rooms), 1fr) auto
		// grid-gap: 8px
		position: relative
		min-width: min-content
		> .room
			position: sticky
			top: calc(var(--pretalx-sticky-date-offset) + var(--pretalx-sticky-top-offset, 0px))
			display: flex
			justify-content: center
			align-items: center
			font-size: 18px
			background-color: $clr-white
			border-bottom: border-separator()
			z-index: 20
			.room-description
				border: 2px solid $clr-grey-400
				border-radius: 100%
				height: 20px
				width: 20px
				padding: 0
				font-weight: bold
				min-width: 0
				button-style(color: $clr-white, text-color: $clr-grey-500)
				margin-left: 8px
				.bunt-tooltip
					height: auto
					width: 200px
					white-space: normal
		.break
			.time-box
				background-color: $clr-grey-500
				.start
					color: $clr-primary-text-dark
				.duration
					color: $clr-secondary-text-dark
			.info
				background-color: $clr-grey-200
				border: none
				justify-content: center
				align-items: center
				.title
					font-size: 16px
					font-weight: 500
					color: $clr-secondary-text-light
					align: center
	.timeslice
		color: $clr-secondary-text-light
		padding: 8px 10px 0 16px
		white-space: nowrap
		position: sticky
		left: 0
		text-align: center
		background-color: $clr-grey-50
		border-top: 1px solid $clr-dividers-light
		z-index: 20
		&.datebreak
			font-weight: 600
			border-top: 3px solid $clr-dividers-light
			white-space: pre
		&.gap
			&::before
				content: ''
				display: block
				width: 6px
				height: calc(100% - 30px - 12px)
				position: absolute
				top: 30px
				left: 50%
				background-image: radial-gradient(circle closest-side, $clr-grey-500 calc(100% - .5px), transparent 100%)
				background-position: 0 0
				background-size: 5px 15px
				background-repeat: repeat-y

	.timeline
		height: 1px
		background-color: $clr-dividers-light
		position: absolute
		width: 100%
		&.datebreak
			height: 3px
	.now
		z-index: 20
		position: sticky
		left: 2px
		&::before
			content: ''
			display: block
			height: 2px
			background-color: $clr-red
			position: absolute
			top: calc(var(--offset) * 100%)
			width: 100%
		&.on-daybreak::before
			background: repeating-linear-gradient(to right, transparent, transparent 5px, $clr-red 5px, $clr-red 10px)
		svg
			position: absolute
			top: calc(var(--offset) * 100% - 11px)
			height: 24px
			width: 24px
			fill: $clr-red
	.bunt-scrollbar-rail-wrapper-x, .bunt-scrollbar-rail-wrapper-y
		z-index: 30
</style>
