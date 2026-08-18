<!--
SPDX-FileCopyrightText: 2020-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
dialog.pretalx-modal#session-modal(ref="modal", @click.stop="close()")
	.dialog-inner(@click.stop="")
		button.close-button(@click="close()") ✕
		template(v-if="session")
			h3.session-title {{ session.title }}
			.talk-layout
				.talk-content
					a.session-image(v-if="session.apiContent?.image", :href="session.apiContent.image", target="_blank", rel="noopener noreferrer")
						img(:src="session.apiContent.image", loading="lazy", :alt="translationMessages.session_image || 'This session’s header image'")
					.text-content
						.abstract(v-if="session.abstract", v-html="renderMarkdown(session.abstract)")
						template(v-if="session.isLoading")
							bunt-progress-circular(size="big", :page="true")
						template(v-else)
							hr(v-if="(session.abstract?.length > 0) && (session.apiContent?.description?.length > 0)")
							.description(v-if="session.apiContent?.description?.length > 0", v-html="renderMarkdown(session.apiContent.description)")
							.answers(v-for="answer in longAnswers", :key="answer.id")
								h4.question {{ getLocalizedString(answer.question.question) }}
								.answer(v-html="renderMarkdown(answer.answer)")
					.talk-speakers(v-if="session.speakers?.length")
						a.talk-speaker-card(v-for="speaker in session.speakers", :key="speaker.code", :href="`#speaker/${speaker.code}`", @click="handleSpeakerClick(speaker, $event)")
							.talk-speaker-avatar
								img(v-if="speaker.avatar", :src="speaker.avatar", :alt="speaker.name")
								.avatar-placeholder(v-else)
									svg(viewBox="0 0 24 24")
										path(fill="currentColor", d="M12,1A5.8,5.8 0 0,1 17.8,6.8A5.8,5.8 0 0,1 12,12.6A5.8,5.8 0 0,1 6.2,6.8A5.8,5.8 0 0,1 12,1M12,15C18.63,15 24,17.67 24,21V23H0V21C0,17.67 5.37,15 12,15Z")
							.talk-speaker-text
								.talk-speaker-name {{ speaker.name }}
								.talk-speaker-bio(v-if="speaker.apiContent?.biography?.length > 0", v-html="renderMarkdown(speaker.apiContent.biography)")
				.talk-sidebar
					.talk-card.talk-card-schedule(:style="{ '--track-color': session.track?.color || 'var(--pretalx-clr-primary)' }")
						.talk-slot(v-for="slot in slots", :key="slot.start.toISO() + '-' + (slot.room ? slot.room.id : '')")
							.talk-slot-time {{ getTimeRange(slot) }}
							.talk-slot-date
								| {{ slot.start.toLocaleString({ day: 'numeric', month: 'short', year: 'numeric' }) }}
								template(v-if="slot.room")
									|  ·
									span.talk-slot-room
										| {{ getLocalizedString(slot.room.name) }}
										bunt-button.room-description(v-if="getLocalizedString(slot.room.description)", :tooltip="getLocalizedString(slot.room.description)", tooltipPlacement="bottom-end") ?
								template(v-if="slot.board_number")
									|  · 
									span.talk-slot-board {{ translationMessages.board || 'Board' }} {{ slot.board_number }}
						.talk-facts
							.talk-fact(v-if="session.track")
								span.talk-track-swatch
								| {{ getLocalizedString(session.track.name) }}{{ submissionType ? ` · ${submissionType}` : '' }}
							.talk-fact(v-else-if="submissionType") {{ submissionType }}
							.talk-fact(v-if="doNotRecord")
								do-not-record-icon
								span {{ translationMessages.not_recorded || 'Not recorded' }}
						.talk-signup(v-if="signupStatus")
							a.talk-signup-action(v-if="signupUrl", :href="signupUrl", target="_blank", rel="noopener") {{ translationMessages.signup || 'Sign up' }}
							.talk-signup-state(v-else) {{ translationMessages.signup_full || 'This session is full' }}
							.talk-signup-note {{ translationMessages.signup_required || 'Requires signup' }}
						.talk-actions
							fav-button(
								:class="{ faved: isFaved }",
								:label="isFaved ? (translationMessages.saved || 'Saved') : (translationMessages.save || 'Save')",
								@toggleFav="$emit('toggleFav', session.id)"
							)
							a.ical-button(v-if="icalUrl", :href="icalUrl")
								svg(viewBox="0 0 448 512", width="14", height="14")
									path(fill="currentColor", d="M96 32V64H48C21.5 64 0 85.5 0 112v48H448V112c0-26.5-21.5-48-48-48H352V32c0-17.7-14.3-32-32-32s-32 14.3-32 32V64H160V32c0-17.7-14.3-32-32-32S96 14.3 96 32zM448 192H0V464c0 26.5 21.5 48 48 48H400c26.5 0 48-21.5 48-48V192z")
								span .ical
					.talk-card.talk-card-details(v-if="shortAnswers.length > 0 || iconAnswers.length > 0 || resources.length > 0")
						h4.talk-card-title {{ translationMessages.details || 'Details' }}
						answer-list(:iconAnswers="iconAnswers", :shortAnswers="shortAnswers")
						template(v-if="resources.length > 0")
							hr(v-if="shortAnswers.length > 0 || iconAnswers.length > 0")
							ul.talk-resources
								li(v-for="resource in resources", :key="resource.id")
									a(:href="resource.resource", target="_blank", rel="noopener noreferrer")
										svg.resource-icon(v-if="isFileResource(resource.resource)", xmlns="http://www.w3.org/2000/svg", viewBox="0 0 384 512", width="16", height="16")
											path(fill="currentColor", d="M64 0C28.7 0 0 28.7 0 64V448c0 35.3 28.7 64 64 64H320c35.3 0 64-28.7 64-64V160H256c-17.7 0-32-14.3-32-32V0H64zM256 0V128H384L256 0zM216 232V334.1l31-31c9.4-9.4 24.6-9.4 33.9 0s9.4 24.6 0 33.9l-72 72c-9.4 9.4-24.6 9.4-33.9 0l-72-72c-9.4-9.4-9.4-24.6 0-33.9s24.6-9.4 33.9 0l31 31V232c0-13.3 10.7-24 24-24s24 10.7 24 24z")
										svg.resource-icon(v-else, xmlns="http://www.w3.org/2000/svg", viewBox="0 0 512 512", width="16", height="16")
											path(fill="currentColor", d="M320 0c-17.7 0-32 14.3-32 32s14.3 32 32 32h82.7L201.4 265.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0L448 109.3V192c0 17.7 14.3 32 32 32s32-14.3 32-32V32c0-17.7-14.3-32-32-32H320zM80 32C35.8 32 0 67.8 0 112V432c0 44.2 35.8 80 80 80H400c44.2 0 80-35.8 80-80V320c0-17.7-14.3-32-32-32s-32 14.3-32 32V432c0 8.8-7.2 16-16 16H80c-8.8 0-16-7.2-16-16V112c0-8.8 7.2-16 16-16H192c17.7 0 32-14.3 32-32s-14.3-32-32-32H80z")
										span {{ resource.description || translationMessages.resource || 'Resource' }}
					.talk-card.talk-card-context(v-if="neighbours.previous || neighbours.next || neighbours.parallel.length")
						h4.talk-card-title {{ translationMessages.around_this_session || 'Around this session' }}
						a.talk-neighbour(v-if="neighbours.previous", :href="sessionUrl(neighbours.previous)", @click="$emit('showSession', neighbours.previous, $event)")
							span.talk-neighbour-icon ↑
							| {{ getTimeRange(neighbours.previous, false) }} {{ getLocalizedString(neighbours.previous.title) }}
						a.talk-neighbour(v-for="neighbour in neighbours.parallel", :key="neighbour.id", :href="sessionUrl(neighbour)", @click="$emit('showSession', neighbour, $event)")
							span.talk-neighbour-icon ↔
							| {{ getTimeRange(neighbour, false) }} {{ getLocalizedString(neighbour.title) }}
						a.talk-neighbour(v-if="neighbours.next", :href="sessionUrl(neighbours.next)", @click="$emit('showSession', neighbours.next, $event)")
							span.talk-neighbour-icon ↓
							| {{ getTimeRange(neighbours.next, false) }} {{ getLocalizedString(neighbours.next.title) }}
		template(v-if="modalContent && modalContent.contentType === 'speaker'")
			.speaker-details
				h3 {{ modalContent.contentObject.name }}
					a.ical-button(v-if="speakerIcalUrl", :href="speakerIcalUrl")
						svg(viewBox="0 0 448 512", width="14", height="14")
							path(fill="currentColor", d="M96 32V64H48C21.5 64 0 85.5 0 112v48H448V112c0-26.5-21.5-48-48-48H352V32c0-17.7-14.3-32-32-32s-32 14.3-32 32V64H160V32c0-17.7-14.3-32-32-32S96 14.3 96 32zM448 192H0V464c0 26.5 21.5 48 48 48H400c26.5 0 48-21.5 48-48V192z")
						span .ical
				.speaker-content.card-content
					.speaker-avatar-container(:class="{ 'outline-container': shortAnswers.length > 0 || iconAnswers.length > 0 }")
						.img-wrapper
							img(v-if="modalContent.contentObject.avatar", :src="modalContent.contentObject.avatar", :alt="modalContent.contentObject.name")
							.avatar-placeholder(v-else)
								svg(viewBox="0 0 24 24")
									path(fill="currentColor", d="M12,1A5.8,5.8 0 0,1 17.8,6.8A5.8,5.8 0 0,1 12,12.6A5.8,5.8 0 0,1 6.2,6.8A5.8,5.8 0 0,1 12,1M12,15C18.63,15 24,17.67 24,21V23H0V21C0,17.67 5.37,15 12,15Z")
						template(v-if="shortAnswers.length > 0 || iconAnswers.length > 0")
							hr
							answer-list(:iconAnswers="iconAnswers", :shortAnswers="shortAnswers")
					.text-content
						template(v-if="modalContent.contentObject.isLoading")
							bunt-progress-circular(size="big", :page="true")
						template(v-else)
							.biography(v-if="modalContent.contentObject.apiContent?.biography?.length > 0", v-html="renderMarkdown(modalContent.contentObject.apiContent.biography)")
			.speaker-sessions
				session(
					v-for="speakerSession in modalContent.contentObject.sessions",
					:key="speakerSession.id",
					:session="speakerSession",
					:showDate="true",
					:now="now",
					:timezone="currentTimezone",
					:locale="locale",
					:hasAmPm="hasAmPm",
					:faved="speakerSession.faved",
					:onHomeServer="onHomeServer",
					@fav="$emit('fav', speakerSession.id)",
					@unfav="$emit('unfav', speakerSession.id)",
				)
</template>

<script>
import { getTimeString, renderMarkdown } from '~/utils'
import localize from '~/mixins/localize'
import AnswerList from '~/components/AnswerList.vue'
import DoNotRecordIcon from '~/components/DoNotRecordIcon.vue'
import FavButton from '~/components/FavButton.vue'
import Session from '~/components/Session.vue'

export default {
	name: 'SessionModal',
	components: { AnswerList, DoNotRecordIcon, FavButton, Session },
	mixins: [localize],
	inject: {
		remoteApiUrl: { default: '' },
		translationMessages: { default: () => ({}) },
		eventUrl: { default: '' }
	},
	props: {
		modalContent: Object,
		currentTimezone: String,
		locale: String,
		hasAmPm: Boolean,
		now: Object,
		onHomeServer: Boolean,
		favs: {
			type: Array,
			default: () => []
		},
		eventUrl: {
			type: String,
			default: ''
		}
	},
	emits: ['toggleFav', 'showSpeaker', 'showSession', 'fav', 'unfav'],
	computed: {
		session () {
			if (!this.modalContent || this.modalContent.contentType !== 'session') return null
			return this.modalContent.contentObject
		},
		isFaved () {
			return !!this.session && this.favs.includes(this.session.id)
		},
		submissionType () {
			return this.getLocalizedString(this.session?.apiContent?.submission_type?.name)
		},
		neighbours () {
			return this.session?.neighbours || { previous: null, next: null, parallel: [] }
		},
		slots () {
			if (!this.session?.start) return []
			return [
				{ start: this.session.start, end: this.session.end, room: this.session.room, board_number: this.session.board_number },
				...(this.session.otherSlots || [])
			]
		},
		nonemptyAnswers () {
			const apiContent = this.modalContent?.contentObject?.apiContent
			if (!apiContent || !apiContent.answers || !apiContent.answers.length) return []
			return apiContent.answers.filter((answer) => {
				return (answer.question.variant === 'file' && answer.answer_file?.length) || answer.answer?.length
			})

		},
		longAnswers () {
			return this.nonemptyAnswers.filter((answer) => answer.question.variant === 'text')
		},
		shortAnswers () {
			return this.nonemptyAnswers.filter((answer) => {
				if (answer.question.variant === 'text') return false
				return !(answer.question.variant === 'url' && answer.question.icon?.length && answer.question.icon !== '-')
			})
		},
		iconAnswers () {
			return this.nonemptyAnswers.filter((answer) => answer.question.variant === 'url' && answer.question.icon?.length && answer.question.icon !== '-')
		},
		resources () {
			const apiContent = this.modalContent?.contentObject?.apiContent
			if (!apiContent?.resources?.length) return []
			return apiContent.resources.filter(r => r.resource)
		},
		signupStatus () {
			if (!this.session) return null
			const fresh = this.session.apiContent?.signup_status
			if (fresh !== undefined && fresh !== null) return fresh
			return this.session.signup_status || null
		},
		signupUrl () {
			if (!this.signupStatus) return ''
			if (this.signupStatus === 'full') return ''
			if (!this.session) return ''
			if (!this.eventUrl) return ''
			const code = this.session.id
			if (!code) return ''
			const base = this.eventUrl.endsWith('/') ? this.eventUrl : `${this.eventUrl}/`
			return `${base}talk/${code}/#signup`
		},
		doNotRecord () {
			if (!this.session) return false
			return !!(this.session.apiContent?.do_not_record ?? this.session.do_not_record)
		},
		icalUrl () {
			if (!this.session) return ''
			const code = this.session.id
			if (!code || !this.eventUrl) return ''
			const base = this.eventUrl.endsWith('/') ? this.eventUrl : `${this.eventUrl}/`
			return `${base}talk/${code}.ics`
		},
		speakerIcalUrl () {
			if (!this.modalContent || this.modalContent.contentType !== 'speaker') return ''
			const code = this.modalContent.contentObject?.code
			if (!code || !this.eventUrl) return ''
			const base = this.eventUrl.endsWith('/') ? this.eventUrl : `${this.eventUrl}/`
			return `${base}speaker/${code}/talks.ics`
		}
	},
	methods: {
		renderMarkdown,
		getTimeRange (slot, withEnd = true) {
			const start = getTimeString(slot.start.setZone(this.currentTimezone), this.locale)
			if (!withEnd || !slot.end) return start
			return `${start}–${getTimeString(slot.end.setZone(this.currentTimezone), this.locale)}`
		},
		sessionUrl (session) {
			if (!this.eventUrl || !session?.id) return ''
			const base = this.eventUrl.endsWith('/') ? this.eventUrl : `${this.eventUrl}/`
			return `${base}talk/${session.id}/`
		},
		showModal () {
			this.$refs.modal?.showModal()
		},
		close () {
			this.$refs.modal?.close()
		},
		handleSpeakerClick (speaker, event) {
			this.$emit('showSpeaker', speaker, event)
		},
		isFileResource (url) {
			try {
				return new URL(url).origin === new URL(this.eventUrl).origin
			} catch { return false }
		}
	}
}
</script>

<style lang="stylus">
.pretalx-modal
	padding: 0
	border-radius: 8px
	border: 0
	box-shadow: 0 -2px 4px rgba(0,0,0,0.06),
		0 1px 3px rgba(0,0,0,0.12),
		0 8px 24px rgba(0,0,0,0.15),
		0 16px 32px rgba(0,0,0,0.09)
	width: calc(100vw - 32px)
	max-width: 848px
	max-height: calc(100vh - 64px)
	overflow-y: auto
	font-size: 16px

	.dialog-inner
		padding: 16px 24px
		margin: 0

	.close-button
		position: absolute
		top: 0
		right: 4px
		background: none
		border: none
		cursor: pointer
		padding: 8px
		color: $clr-grey-600
		font-size: 22px
		font-weight: bold
		&:hover
			background: none
			color: $clr-grey-900

	h3
		margin: 8px 0
		display: flex
		align-items: center

	.session-title
		margin-right: 24px

	.ampm
		margin-left: 4px

	.ical-button
		display: inline-flex
		align-items: center
		gap: 4px
		font-size: 14px
		font-weight: normal
		color: var(--pretalx-clr-primary-text)
		text-decoration: none
		&:hover
			text-decoration: underline
		svg
			flex: none

	.speaker-details .ical-button
		margin-left: 12px

	.talk-layout
		display: flex
		flex-direction: column
		gap: 16px

		.talk-content
			order: 2
			min-width: 0
		.talk-card-schedule
			order: 1
		.talk-card-details
			order: 3
		.talk-card-context
			order: 4

	.talk-sidebar
		display: contents

	.session-image
		display: block
		margin-bottom: 12px
		img
			display: block
			max-width: 100%
			max-height: 320px
			border-radius: 6px

	.card-content
			display: flex
			flex-direction: column

	.text-content
			margin-bottom: 8px
			.abstract
				font-weight: bold
			p
				font-size: 16px
			hr
				color: #ced4da
				height: 0
				border: 0
				border-top: 1px solid #e0e0e0
				margin: 16px 0
			.answers
				margin-top: 16px
				.question
					margin: 0 0 4px 0
					font-size: 18px
					font-weight: 600

	.talk-speakers
		display: grid
		grid-template-columns: 1fr
		gap: 12px
		margin-top: 16px

	.talk-speaker-card
		display: flex
		align-items: center
		gap: 12px
		padding: 8px
		min-height: 44px
		border: 1px solid #ced4da
		border-radius: 6px
		color: var(--pretalx-clr-primary-text)
		text-decoration: none
		overflow: hidden
		cursor: pointer

		@media (hover: hover)
			&:hover
				text-decoration: none
				border-color: var(--pretalx-clr-primary)
				box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24)

		.talk-speaker-avatar
			flex: none
			width: 56px
			height: 56px
			border-radius: 50%
			overflow: hidden
			img, .avatar-placeholder
				width: 56px
				height: 56px
			img
				object-fit: cover
			.avatar-placeholder
				background: rgba(0,0,0,0.1)
				display: flex
				align-items: center
				justify-content: center
				svg
					width: 60%
					height: 60%
					color: rgba(0,0,0,0.3)
		.talk-speaker-text
			min-width: 0
		.talk-speaker-name
			font-weight: 600
			overflow: hidden
			text-overflow: ellipsis
		.talk-speaker-bio
			color: $clr-grey-600
			font-size: 14px
			display: -webkit-box
			-webkit-line-clamp: 2
			line-clamp: 2
			-webkit-box-orient: vertical
			overflow: hidden
			p
				display: inline
				margin-bottom: 0
			p + p::before
				content: " "

	.talk-card
		box-sizing: border-box
		border: 1px solid #ced4da
		border-radius: 6px
		padding: 12px 16px
		*
			box-sizing: border-box

		hr
			color: #ced4da
			height: 0
			border: 0
			border-top: 1px solid #e0e0e0
			margin: 8px 0

		.talk-card-title
			margin: 0 0 8px 0
			font-size: 12px
			font-weight: 600
			letter-spacing: 0.06em
			text-transform: uppercase
			color: $clr-grey-600

	.talk-card-schedule
		border: 2px solid var(--pretalx-clr-primary)
		box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24)

		.talk-slot
			margin-bottom: 8px
		.talk-slot-time
			font-size: 22px
			font-weight: 700
			line-height: 1.3
		// Multiple slots
		&:has(.talk-slot + .talk-slot) .talk-slot-time
			font-size: 17px
		.talk-slot-date
			color: $clr-grey-600
			font-size: 14px
		.talk-slot-room
			margin-left: 4px
			font-weight: 700
			overflow-wrap: break-word
			.room-description
				display: inline-flex
				min-width: 0
				height: 16px
				width: 16px
				margin-left: 4px
				padding: 0
				vertical-align: text-bottom
				border-radius: 50%
				border: 1px solid $clr-grey-600
				color: $clr-grey-600
				font-size: 11px
				font-weight: normal
				.bunt-button-text
					line-height: 14px
					margin: auto

		.talk-facts
			font-size: 14px
			color: $clr-grey-600
			&:has(> *)
				border-top: 1px solid #ced4da
				margin-top: 8px
				padding-top: 8px
		.talk-fact
			display: flex
			align-items: baseline
			gap: 4px
			overflow-wrap: anywhere
			svg
				width: 18px
				height: 18px
				align-self: center
		.talk-track-swatch
			flex: none
			width: 8px
			height: 8px
			border-radius: 2px
			background-color: var(--track-color)

		.talk-signup
			margin-top: 12px
			.talk-signup-action, .talk-signup-state
				width: 100%
				min-height: 44px
				display: flex
				align-items: center
				justify-content: center
				gap: 6px
				padding: 0 12px
				border: 1px solid var(--pretalx-clr-primary)
				border-radius: 4px
				text-decoration: none
			.talk-signup-action
				background-color: var(--pretalx-clr-primary)
				color: #fff
				&:hover
					background-color: var(--pretalx-clr-primary-text-dark)
					border-color: var(--pretalx-clr-primary-text-dark)
			.talk-signup-state
				border-color: $clr-grey-400
				color: $clr-grey-600
		.talk-signup-note
			margin-top: 4px
			font-size: 13px
			color: $clr-grey-600
			text-align: center

		.talk-actions
			display: flex
			gap: 8px
			&:has(> *)
				margin-top: 12px
			> *
				flex: 1
				min-height: 44px
				display: flex
				align-items: center
				justify-content: center
				gap: 6px
				white-space: nowrap
				padding: 0 12px
				border: 1px solid var(--pretalx-clr-primary)
				border-radius: 4px
				color: var(--pretalx-clr-primary-text)
			.ical-button:hover
				background-color: var(--pretalx-clr-primary)
				color: #fff
				text-decoration: none

	.talk-card-context
		font-size: 14px
		.talk-neighbour
			display: block
			min-height: 44px
			line-height: 44px
			white-space: nowrap
			overflow: hidden
			text-overflow: ellipsis
			color: $clr-grey-600
			text-decoration: none
			cursor: pointer
			&:hover
				color: var(--pretalx-clr-primary-text)
			.talk-neighbour-icon
				margin-right: 4px

	.talk-card-details
		font-size: 14px
		.inline-answer:last-child
			margin-bottom: 0
		.talk-resources
			list-style: none
			padding-left: 0
			margin: 0
			li
				overflow-wrap: anywhere
			a
				color: var(--pretalx-clr-primary-text)
			.resource-icon
				display: inline-block
				vertical-align: middle
				margin-right: 4px

	.img-wrapper
		padding: 4px 16px 4px 4px
		width: 140px
		height: 140px
		img, .avatar-placeholder
			width: 140px
			height: 140px
			border-radius: 50%
			box-shadow: rgba(0, 0, 0, 0.12) 0px 1px 3px 0px, rgba(0, 0, 0, 0.24) 0px 1px 2px 0px

		img
			object-fit: cover

		.avatar-placeholder
			background: rgba(0,0,0,0.1)
			display: flex
			align-items: center
			justify-content: center
			svg
				width: 60%
				height: 60%
				color: rgba(0,0,0,0.3)

	.speaker-details
		h3
			margin-bottom: 0
		.speaker-content
			display: flex
			flex-direction: row-reverse
			align-items: flex-start
			justify-content: space-between
			margin-bottom: 16px

			.biography
					margin-top: 8px

		.speaker-avatar-container
			&.outline-container
				border: 1px solid var(--pretalx-clr-primary)
				box-shadow: rgba(0, 0, 0, 0.24) 0px 1px 2px 0px
				border-radius: 6px
				padding: 12px
				margin-left: 8px
				display: flex
				flex-direction: column
				align-items: center

				.img-wrapper
					padding: 0 0 8px 0

			hr
				color: #ced4da
				height: 0
				border: 0
				border-top: 1px solid #e0e0e0
				margin: 8px 0
				align-self: stretch

			.answers
				.icon-group
					justify-content: center

				.inline-answer
					margin-top: 8px

	@media (min-width: 800px)
		.talk-layout
			display: grid
			grid-template-columns: minmax(0, 1fr) 280px
			grid-template-areas: "content sidebar"
			column-gap: 24px
			align-items: start

			.talk-content
				grid-area: content

		.talk-sidebar
			display: flex
			flex-direction: column
			gap: 16px
			grid-area: sidebar

		.talk-speakers
			grid-template-columns: repeat(2, minmax(0, 1fr))

			> *:last-child:nth-child(odd)
				grid-column: 1 / -1

		.session-image img
			max-width: 480px

	@media (max-width: 768px)
		.speaker-details
			.speaker-content
				display: block

				.speaker-avatar-container
					float: right
					width: auto
					max-width: 200px
					margin-left: 16px
					margin-bottom: 16px

					&.outline-container
						margin-right: 0

				.text-content
					display: inline

					.biography
						display: inline

			&::after
				content: ""
				display: table
				clear: both

		.speaker-sessions
			clear: both
			margin: 0 -8px /* Counteract default session block margins, so that these align with speaker blocks and text blocks */
</style>
