<!--
SPDX-FileCopyrightText: 2020-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
.c-linear-schedule(v-scrollbar.y="")
	.bucket(v-for="({date, sessions}, index) of sessionBuckets")
		.bucket-label(:ref="getBucketName(date)", :data-date="date.toISO()")
			.day(v-if="index === 0 || date.startOf('day').diff(sessionBuckets[index - 1].date.startOf('day')).shiftTo('days').days > 0")  {{ date.setZone(timezone).toLocaleString({ weekday: 'long', day: 'numeric', month: 'long' }) }}
			.time {{ date.setZone(timezone).toLocaleString({ hour: 'numeric', minute: 'numeric' }) }}
			template(v-for="session of sessions")
				session(
					v-if="isProperSession(session)",
					:session="session",
					:now="now",
					:timezone="timezone",
					:locale="locale",
					:hasAmPm="hasAmPm",
					:faved="session.id && favs.includes(session.id)",
					:signedUp="session.id && signups.includes(session.id)",
					:onHomeServer="onHomeServer",
					@fav="$emit('fav', session.id)",
					@unfav="$emit('unfav', session.id)"
				)
				.break(v-else)
					.title {{ getLocalizedString(session.title) }}
</template>
<script>
import { DateTime } from 'luxon'
import { isProperSession } from '~/utils'
import localize from '~/mixins/localize'
import scheduleScrollMixin from '~/mixins/scheduleScroll'
import Session from './Session'

export default {
	components: { Session },
	mixins: [localize, scheduleScrollMixin],
	props: {
		sessions: Array,
		rooms: Array,
		locale: String,
		hasAmPm: Boolean,
		timezone: String,
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
		scrollParent: Element,
		onHomeServer: Boolean
	},
	data () {
		return {
			isProperSession
		}
	},
	computed: {
		nowBucketIndex () {
			// Find the bucket index for "now" - returns -1 if event hasn't started
			return this.sessionBuckets.findIndex(bucket => this.now < bucket.date)
		},
		hasNow () {
			// "Now" is valid if the event has started (nowBucketIndex >= 0)
			return this.nowBucketIndex >= 0
		},
		sessionBuckets () {
			const buckets = {}
			for (const session of this.sessions) {
				// Convert session start to current timezone for consistent grouping
				const sessionInTimezone = session.start.setZone(this.timezone)
				const key = this.getBucketName(sessionInTimezone)
				if (!buckets[key]) {
					buckets[key] = []
				}
				if (!session.id) {
					// Remove duplicate breaks, meaning same start, end and text
					session.break_id = `${session.start}${session.end}${this.getLocalizedString(session.title)}`
					if (buckets[key].filter(s => s.break_id === session.break_id).length === 0) buckets[key].push(session)
				} else {
					buckets[key].push(session)
				}
			}
			return Object.entries(buckets).map(([date, sessions]) => ({
				date: sessions[0].start.setZone(this.timezone),
				// sort by room for stable sort across time buckets
				sessions: sessions.sort((a, b) => this.rooms.findIndex(room => room.id === a.room.id) - this.rooms.findIndex(room => room.id === b.room.id))
			}))
		}
	},
	async mounted () {
		await this.$nextTick()
		this.setupIntersectionObserver()
	},
	methods: {
		scrollToNow () {
			if (!this.hasNow) return
			const nowBucket = this.sessionBuckets[Math.max(0, this.nowBucketIndex - 1)]
			const el = this.$refs[this.getBucketName(nowBucket.date)]?.[0]
			if (el) {
				const scrollTop = el.offsetTop - 90
				const scrollEl = this.scrollParent
				if (scrollEl) {
					scrollEl.scrollTo({ top: scrollTop, behavior: 'smooth' })
				} else {
					const rect = this.$parent.$el.getBoundingClientRect()
					window.scroll({ top: scrollTop + rect.top + window.scrollY, behavior: 'smooth' })
				}
			}
		},
		observeElements() {
			// LinearSchedule-specific: observe day boundary buckets
			let lastBucket
			for (const [ref, el] of Object.entries(this.$refs)) {
				if (!ref.startsWith('bucket')) continue
				if (!el || !el[0]) continue
				const date = DateTime.fromISO(el[0].dataset.date, { zone: this.timezone })
				if (lastBucket) {
					if (lastBucket.toISODate() === date.toISODate()) continue
				}
				lastBucket = date
				this.observer.observe(el[0])
			}
		},
		getBucketName (date) {
			return `bucket-${date.toFormat('yyyy-LL-dd-HH-mm')}`
		},
		changeDay (day) {
			// Find a session bucket that matches the target day when converted to timezone
			const dayBucket = this.sessionBuckets.find(bucket => {
				const bucketDate = bucket.date.setZone(this.timezone).toISODate()
				return day === bucketDate
			})
			if (!dayBucket) return

			const el = this.$refs[this.getBucketName(dayBucket.date)]?.[0]
			if (el) {
				this.programmaticScrollTo(el)
			}
		},
		calculateScrollTop(element) {
			const rect = this.$parent.$el.getBoundingClientRect()
			return element.offsetTop + rect.top + window.scrollY - 8
		},
	}
}
</script>
<style lang="stylus">
.c-linear-schedule
	display: flex
	flex-direction: column
	min-height: 0
	.bucket
		padding-top: 8px
		.bucket-label
			font-size: 14px
			font-weight: 500
			color: $clr-secondary-text-light
			padding-left: 16px
			.day
				font-weight: 600
		.break
			z-index: 10
			margin: 8px
			padding: 8px
			border-radius: 4px
			background-color: $clr-grey-200
			display: flex
			justify-content: center
			align-items: center
			.title
				font-size: 20px
				font-weight: 500
				color: $clr-secondary-text-light
</style>
