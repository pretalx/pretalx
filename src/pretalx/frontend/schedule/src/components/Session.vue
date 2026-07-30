<!--
SPDX-FileCopyrightText: 2020-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
a.c-linear-schedule-session(:class="{faved, 'signed-up': signedUp, 'signup-full': isFull, 'signup-required': requiresSignup}", :style="style", :href="link", :target="linkTarget", @click="onSessionLinkClick($event, session)")
	.time-box
		.start(:class="{'has-ampm': hasAmPm}")
			.date(v-if="showDate") {{ shortDate }}
			.time {{ startTime.time }}
			.ampm(v-if="startTime.ampm") {{ startTime.ampm }}
		.duration {{ getPrettyDuration(session.start, session.end) }}
		.buffer
		.is-live(v-if="isLive") live
	.info
		.title
			| {{ getLocalizedString(session.title) }}
		.speakers(v-if="session.speakers")
			.avatars
				template(v-for="speaker of session.speakers", :key="speaker.code")
					img(v-if="speaker.avatar_thumbnail_tiny", :src="speaker.avatar_thumbnail_tiny")
					img(v-else-if="speaker.avatar_thumbnail_default", :src="speaker.avatar_thumbnail_default")
					img(v-else-if="speaker.avatar", :src="speaker.avatar")
			.names {{ session.speakers.map(s => s.name).join(', ') }}
		.abstract(v-if="showAbstract", v-html="abstractText")
		.bottom-info
			.track(v-if="session.track") {{ getLocalizedString(session.track.name) }}
			.room(v-if="showRoom && session.room", :title="getLocalizedString(session.room.name)") {{ getLocalizedString(session.room.name) }}
			i.fa.fa-user-plus.signup-icon(v-if="requiresSignup && !isFull && !signedUp", :title="translationMessages?.signup_required || 'Requires attendee signup'", :aria-label="translationMessages?.signup_required || 'Requires attendee signup'")
			i.fa.fa-user-times.signup-icon.full(v-if="isFull && !signedUp", :title="translationMessages?.signup_full || 'This session is full'", :aria-label="translationMessages?.signup_full || 'This session is full'")
			i.fa.fa-calendar-check-o.signed-up-icon(v-if="signedUp", :title="translationMessages?.signup_signed_up || 'You are signed up for this session'", :aria-label="translationMessages?.signup_signed_up || 'You are signed up for this session'")
			do-not-record-icon(v-if="session.do_not_record")
	.session-icons
		fav-button(:class="{'d-print-none': !faved}", @toggleFav="toggleFav")

</template>
<script>
import { DateTime } from 'luxon'
import { getPrettyDuration, getSessionTime, renderMarkdown } from '~/utils'
import localize from '~/mixins/localize'
import DoNotRecordIcon from '~/components/DoNotRecordIcon.vue'
import FavButton from '~/components/FavButton.vue'

export default {
	components: {
		DoNotRecordIcon,
		FavButton
	},
	mixins: [localize],
	inject: {
		eventUrl: { default: null },
		linkTarget: { default: '_self' },
		translationMessages: { default: () => ({}) },
		generateSessionLinkUrl: {
			default () {
				return ({eventUrl, session}) => {
					if (!this.onHomeServer) return `#session/${session.id}/`
					return`${eventUrl}talk/${session.id}/`
				}
			}
		},
		onSessionLinkClick: {
			default () {
				return () => {}
			}
		}
	},
	props: {
		now: Object,
		session: Object,
		showAbstract: {
			type: Boolean,
			default: true
		},
		showRoom: {
			type: Boolean,
			default: true
		},
		showDate: {
			type: Boolean,
			default: false
		},
		faved: {
			type: Boolean,
			default: false
		},
		signedUp: {
			type: Boolean,
			default: false
		},
		hasAmPm: {
			type: Boolean,
			default: false
		},
		locale: String,
		timezone: String,
		onHomeServer: Boolean
	},
	emits: ['fav', 'unfav'],
	computed: {
		link () {
			return this.generateSessionLinkUrl({eventUrl: this.eventUrl, session: this.session})
		},
		style () {
			return {
				'--track-color': this.session.track?.color || 'var(--pretalx-clr-primary)'
			}
		},
		startTime () {
			return getSessionTime(this.session, this.timezone, this.locale, this.hasAmPm)
		},
		shortDate () {
			return this.session.start.setZone(this.timezone).toLocaleString({
				month: 'short',
				day: 'numeric'
			})
		},
		isLive () {
			return this.session.start < this.now && this.session.end > this.now
		},
		requiresSignup () {
			return !!this.session.signup_status
		},
		isFull () {
			return this.session.signup_status === 'full'
		},
		abstractText () {
			let abstractText = this.session.abstract
			try {
				const fullAbstract = renderMarkdown(abstractText)
				if (fullAbstract.length && fullAbstract.includes("<table>")) {
					const tableStart = abstractText.indexOf("|")
					if (tableStart >= 0) {
						abstractText = abstractText.slice(0, tableStart)
					}
				}
				return renderMarkdown(abstractText, true)
			} catch (error) {
				return abstractText
			}
		}
	},
	methods: {
		getPrettyDuration,
		toggleFav () {
			if (this.faved) {
				this.$emit('unfav', this.session.id)
			} else {
				this.$emit('fav', this.session.id)
			}
		}
	}
}
</script>
<style lang="stylus">
@import 'session'
.c-linear-schedule-session, .break
	session-layout()
	z-index: 10
	color: rgb(13 15 16)
	font-size: 14px
	.time-box
		background-color: var(--track-color)
		.start
			color: $clr-primary-text-dark
			.date
				margin-bottom: 4px
				white-space: nowrap
		.duration
			color: $clr-secondary-text-dark
		.buffer
			flex: auto
		.is-live
			align-self: stretch
			text-align: center
			font-weight: 600
			padding: 2px 4px
			border-radius: 4px
			margin: 0 -10px 0 -6px // HACK
			background-color: $clr-danger
			color: $clr-primary-text-dark
			letter-spacing: 0.5px
			text-transform: uppercase
	.info
		border: border-separator()
		border-left: none
		border-radius: 0 6px 6px 0
		background-color: $clr-white
		.title
			font-size: 16px
			margin-bottom: 4px
			margin-right: 20px
			overflow-wrap: anywhere
		.speakers
			color: $clr-secondary-text-light
			display: flex
			.avatars
				flex: none
				display: flex
				> *:not(:first-child)
					margin-left: -20px
				img
					background-color: $clr-white
					border-radius: 50%
					height: 24px
					width: @height
					margin: 0 8px 0 0
					object-fit: cover
			.names
				line-height: 24px
				overflow-wrap: anywhere
		.abstract
			margin: 8px 0 12px 0
			// TODO make this take up more space if available?
			session-text-clamp(3, false)
			font-weight: normal
		.bottom-info
			.room
				flex: 1
				text-align: right
				color: $clr-secondary-text-light
				ellipsis()
				padding-right: 12px
			.signup-icon
				flex: none
				font-size: 18px
				line-height: 20px
				color: var(--pretalx-clr-primary)
				margin-left: 6px
			.signup-icon.full
				color: $clr-danger
			.signed-up-icon
				flex: none
				font-size: 18px
				line-height: 20px
				color: var(--pretalx-clr-success)
				margin-left: 6px
			.do-not-record
				flex: none
				width: 20px
				height: 20px
				margin-left: 6px
	.session-icons
		position: absolute
		top: 2px
		right: 2px
		display: flex
		.btn-fav-container
			margin-top: 2px
			display: inline-flex
			icon-button-style(style: clear)
			padding: 2px
			width: 32px
			height: 32px
	.c-grid-schedule &
		.info .title
			session-text-clamp(3)
			session-text-expand()
		.info .speakers .names
			session-text-clamp(2)
			session-text-expand(6)
	@media (hover: hover)
		&:hover
			.info
				border: 1px solid var(--track-color)
				border-left: none
@media(hover: none)
	.c-linear-schedule-session .session-icons .btn-fav-container
		display: inline-flex
</style>
