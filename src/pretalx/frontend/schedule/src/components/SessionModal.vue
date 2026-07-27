<!--
SPDX-FileCopyrightText: 2020-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
dialog.pretalx-modal#session-modal(ref="modal", @click.stop="close()")
	.dialog-inner(@click.stop="")
		button.close-button(@click="close()") ✕
		template(v-if="modalContent && modalContent.contentType === 'session'")
			h3 {{ modalContent.contentObject.title }}
				.button-container(:class="modalContent.contentObject.faved ? 'faved' : ''")
					fav-button(@toggleFav="$emit('toggleFav', modalContent.contentObject.id)")
					a.ical-button(v-if="icalUrl", :href="icalUrl")
						svg(viewBox="0 0 448 512", width="14", height="14")
							path(fill="currentColor", d="M96 32V64H48C21.5 64 0 85.5 0 112v48H448V112c0-26.5-21.5-48-48-48H352V32c0-17.7-14.3-32-32-32s-32 14.3-32 32V64H160V32c0-17.7-14.3-32-32-32S96 14.3 96 32zM448 192H0V464c0 26.5 21.5 48 48 48H400c26.5 0 48-21.5 48-48V192z")
						span .ical

			.card-content
				.facts
					.time
						span {{ modalContent.contentObject.start.toLocaleString({ weekday: 'long', day: 'numeric', month: 'long' }) }}, {{ getSessionTime(modalContent.contentObject, currentTimezone, locale, hasAmPm).time }}
						span.ampm(v-if="getSessionTime(modalContent.contentObject, currentTimezone, locale, hasAmPm).ampm") {{ getSessionTime(modalContent.contentObject, currentTimezone, locale, hasAmPm).ampm }}
					.room(v-if="modalContent.contentObject.room")
						| {{ getLocalizedString(modalContent.contentObject.room.name) }}
						bunt-button.room-description(v-if="getLocalizedString(modalContent.contentObject.room.description)", :tooltip="getLocalizedString(modalContent.contentObject.room.description)", tooltipPlacement="bottom-end") ?
					.track(v-if="modalContent.contentObject.track", :style="{ color: modalContent.contentObject.track.color }") {{ getLocalizedString(modalContent.contentObject.track.name) }}
					.language(v-if="isMultilang && modalContent.contentObject.content_locale") {{ getLanguageName(modalContent.contentObject.content_locale) }}
					.do-not-record-fact(v-if="doNotRecord")
						do-not-record-icon
						span {{ translationMessages.not_recorded || 'Not recorded' }}
				.other-slots(v-if="modalContent.contentObject.otherSlots?.length")
					span.other-slots-label {{ translationMessages.also_scheduled || 'Also takes place at:' }}
					.other-slot(v-for="slot in modalContent.contentObject.otherSlots", :key="slot.start.toISO() + '-' + (slot.room ? slot.room.id : '')")
						span {{ slot.start.toLocaleString({ weekday: 'long', day: 'numeric', month: 'long' }) }}, {{ getSessionTime(slot, currentTimezone, locale, hasAmPm).time }}
						span.ampm(v-if="getSessionTime(slot, currentTimezone, locale, hasAmPm).ampm") {{ getSessionTime(slot, currentTimezone, locale, hasAmPm).ampm }}
						span(v-if="slot.room") , {{ getLocalizedString(slot.room.name) }}
				.signup-banner(v-if="signupStatus", :class="{full: signupStatus === 'full'}")
					i.fa(:class="signupStatus === 'full' ? 'fa-user-times' : 'fa-user-plus'")
					template(v-if="signupStatus === 'full'")
						span.signup-status-label {{ translationMessages.signup_full || 'This session is full' }}
					template(v-else)
						span.signup-status-label {{ translationMessages.signup_required || 'Requires attendee signup' }}
						a.signup-link(v-if="signupUrl", :href="signupUrl", target="_blank", rel="noopener") {{ translationMessages.signup || 'Sign up' }}
				a.session-image(v-if="modalContent.contentObject.apiContent?.image", :href="modalContent.contentObject.apiContent.image", target="_blank", rel="noopener noreferrer")
					img(:src="modalContent.contentObject.apiContent.image", loading="lazy", :alt="translationMessages.session_image || 'This session’s header image'")
				.text-content
					.abstract(v-if="modalContent.contentObject.abstract", v-html="renderMarkdown(modalContent.contentObject.abstract)")
					template(v-if="modalContent.contentObject.isLoading")
						bunt-progress-circular(size="big", :page="true")
					template(v-else)
						hr(v-if="(modalContent.contentObject.abstract?.length > 0) && (modalContent.contentObject.apiContent?.description?.length > 0)")
						.description(v-if="modalContent.contentObject.apiContent?.description?.length > 0", v-html="renderMarkdown(modalContent.contentObject.apiContent.description)")
						template(v-if="shortAnswers.length > 0 || iconAnswers.length > 0")
							hr
							answer-list(:iconAnswers="iconAnswers", :shortAnswers="shortAnswers")
						template(v-if="resources.length > 0")
							hr
							.resources
								strong {{ translationMessages.see_also || 'See also:' }}
								template(v-if="resources.length === 1")
									|
									a(:href="resources[0].resource", target="_blank", rel="noopener noreferrer")
										svg.resource-icon(v-if="isFileResource(resources[0].resource)", xmlns="http://www.w3.org/2000/svg", viewBox="0 0 384 512", width="16", height="16")
											path(fill="currentColor", d="M64 0C28.7 0 0 28.7 0 64V448c0 35.3 28.7 64 64 64H320c35.3 0 64-28.7 64-64V160H256c-17.7 0-32-14.3-32-32V0H64zM256 0V128H384L256 0zM216 232V334.1l31-31c9.4-9.4 24.6-9.4 33.9 0s9.4 24.6 0 33.9l-72 72c-9.4 9.4-24.6 9.4-33.9 0l-72-72c-9.4-9.4-9.4-24.6 0-33.9s24.6-9.4 33.9 0l31 31V232c0-13.3 10.7-24 24-24s24 10.7 24 24z")
										svg.resource-icon(v-else, xmlns="http://www.w3.org/2000/svg", viewBox="0 0 512 512", width="16", height="16")
											path(fill="currentColor", d="M320 0c-17.7 0-32 14.3-32 32s14.3 32 32 32h82.7L201.4 265.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0L448 109.3V192c0 17.7 14.3 32 32 32s32-14.3 32-32V32c0-17.7-14.3-32-32-32H320zM80 32C35.8 32 0 67.8 0 112V432c0 44.2 35.8 80 80 80H400c44.2 0 80-35.8 80-80V320c0-17.7-14.3-32-32-32s-32 14.3-32 32V432c0 8.8-7.2 16-16 16H80c-8.8 0-16-7.2-16-16V112c0-8.8 7.2-16 16-16H192c17.7 0 32-14.3 32-32s-14.3-32-32-32H80z")
										span {{ resources[0].description || translationMessages.resource || 'Resource' }}
								ul(v-else)
									li(v-for="resource in resources", :key="resource.id")
										a(:href="resource.resource", target="_blank", rel="noopener noreferrer")
											svg.resource-icon(v-if="isFileResource(resource.resource)", xmlns="http://www.w3.org/2000/svg", viewBox="0 0 384 512", width="16", height="16")
												path(fill="currentColor", d="M64 0C28.7 0 0 28.7 0 64V448c0 35.3 28.7 64 64 64H320c35.3 0 64-28.7 64-64V160H256c-17.7 0-32-14.3-32-32V0H64zM256 0V128H384L256 0zM216 232V334.1l31-31c9.4-9.4 24.6-9.4 33.9 0s9.4 24.6 0 33.9l-72 72c-9.4 9.4-24.6 9.4-33.9 0l-72-72c-9.4-9.4-9.4-24.6 0-33.9s24.6-9.4 33.9 0l31 31V232c0-13.3 10.7-24 24-24s24 10.7 24 24z")
											svg.resource-icon(v-else, xmlns="http://www.w3.org/2000/svg", viewBox="0 0 512 512", width="16", height="16")
												path(fill="currentColor", d="M320 0c-17.7 0-32 14.3-32 32s14.3 32 32 32h82.7L201.4 265.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0L448 109.3V192c0 17.7 14.3 32 32 32s32-14.3 32-32V32c0-17.7-14.3-32-32-32H320zM80 32C35.8 32 0 67.8 0 112V432c0 44.2 35.8 80 80 80H400c44.2 0 80-35.8 80-80V320c0-17.7-14.3-32-32-32s-32 14.3-32 32V432c0 8.8-7.2 16-16 16H80c-8.8 0-16-7.2-16-16V112c0-8.8 7.2-16 16-16H192c17.7 0 32-14.3 32-32s-14.3-32-32-32H80z")
											span {{ resource.description || translationMessages.resource || 'Resource' }}
			.speakers(v-if="modalContent.contentObject.speakers")
				a.speaker.inner-card(v-for="speaker in modalContent.contentObject.speakers", :key="speaker.code", :href="`#speaker/${speaker.code}`", @click="handleSpeakerClick(speaker, $event)")
					.img-wrapper
						img(v-if="speaker.avatar", :src="speaker.avatar", :alt="speaker.name")
						.avatar-placeholder(v-else)
							svg(viewBox="0 0 24 24")
								path(fill="currentColor", d="M12,1A5.8,5.8 0 0,1 17.8,6.8A5.8,5.8 0 0,1 12,12.6A5.8,5.8 0 0,1 6.2,6.8A5.8,5.8 0 0,1 12,1M12,15C18.63,15 24,17.67 24,21V23H0V21C0,17.67 5.37,15 12,15Z")
					.inner-card-content
						span {{ speaker.name }}
						p.biography(v-if="speaker.apiContent?.biography?.length > 0", v-html="renderMarkdown(speaker.apiContent.biography)")
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
					v-for="session in modalContent.contentObject.sessions",
					:key="session.id",
					:session="session",
					:showDate="true",
					:now="now",
					:timezone="currentTimezone",
					:locale="locale",
					:hasAmPm="hasAmPm",
					:faved="session.faved",
					:onHomeServer="onHomeServer",
					@fav="$emit('fav', session.id)",
					@unfav="$emit('unfav', session.id)",
				)
</template>

<script>
import { getSessionTime, renderMarkdown } from '~/utils'
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
		isMultilang: Boolean,
		eventUrl: {
			type: String,
			default: ''
		}
	},
	emits: ['toggleFav', 'showSpeaker', 'fav', 'unfav'],
	computed: {
		nonemptyAnswers () {
			const apiContent = this.modalContent.contentObject.apiContent
			if (!apiContent || !apiContent.answers || !apiContent.answers.length) return []
			return apiContent.answers.filter((answer) => {
				return (answer.question.variant === 'file' && answer.answer_file?.length) || answer.answer?.length
			})

		},
		shortAnswers () {
			return this.nonemptyAnswers.filter((answer) => {
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
			if (!this.modalContent || this.modalContent.contentType !== 'session') return null
			const fresh = this.modalContent.contentObject?.apiContent?.signup_status
			if (fresh !== undefined && fresh !== null) return fresh
			return this.modalContent.contentObject?.signup_status || null
		},
		signupUrl () {
			if (!this.signupStatus) return ''
			if (this.signupStatus === 'full') return ''
			if (!this.modalContent || this.modalContent.contentType !== 'session') return ''
			if (!this.eventUrl) return ''
			const code = this.modalContent.contentObject?.id
			if (!code) return ''
			const base = this.eventUrl.endsWith('/') ? this.eventUrl : `${this.eventUrl}/`
			return `${base}talk/${code}/#signup`
		},
		doNotRecord () {
			if (!this.modalContent || this.modalContent.contentType !== 'session') return false
			const contentObject = this.modalContent.contentObject
			return !!(contentObject?.apiContent?.do_not_record ?? contentObject?.do_not_record)
		},
		icalUrl () {
			if (!this.modalContent || this.modalContent.contentType !== 'session') return ''
			const code = this.modalContent.contentObject?.id
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
		getSessionTime,
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

		.button-container
			display: flex
			align-items: center

	.ampm
		margin-left: 4px

	.ical-button
		display: inline-flex
		align-items: center
		gap: 4px
		margin-left: 12px
		font-size: 14px
		font-weight: normal
		color: var(--pretalx-clr-primary-text)
		text-decoration: none
		&:hover
			text-decoration: underline
		svg
			flex: none

	.facts
		display: flex
		flex-wrap: wrap
		color: $clr-grey-600
		margin-bottom: 8px
		border-bottom: 1px solid $clr-grey-300
		&>*
			margin-right: 4px
			margin-bottom: 8px
			&:not(:last-child):after
				content: ','
		.room .room-description
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
			.bunt-button-text
				line-height: 14px
				margin: auto
		.do-not-record-fact
			display: inline-flex
			align-items: center
			gap: 4px
			svg
				width: 18px
				height: 18px

	.other-slots
		color: $clr-grey-600
		font-size: 14px
		margin: -4px 0 12px
		.other-slots-label
			font-weight: 600
			margin-right: 4px
		.other-slot
			display: inline
			&:not(:last-child):after
				content: ';'
				margin-right: 4px

	.session-image
		display: block
		margin-bottom: 12px
		img
			display: block
			max-width: 100%
			max-height: 320px
			border-radius: 6px

	.signup-banner
		display: flex
		align-items: center
		gap: 8px
		padding: 8px 12px
		margin-bottom: 12px
		border-radius: 6px
		background-color: rgba(46, 125, 50, 0.1)
		color: $clr-success
		font-size: 14px
		.fa
			font-size: 16px
		.signup-status-label
			flex: 1
		.signup-link
			color: inherit
			font-weight: 600
			text-decoration: underline
			&:hover
				text-decoration: none
		&.full
			background-color: rgba(178, 62, 101, 0.1)
			color: $clr-danger

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

	.resources
		strong
			margin-right: 4px

		a[href]
			color: var(--pretalx-clr-primary-text)

		.resource-icon
			display: inline-block
			vertical-align: middle
			margin-right: 4px

		ul
			margin: 4px 0 0 0
			padding-left: 20px
			li
				margin-bottom: 4px

	.inner-card
		display: flex
		margin-bottom: 12px
		cursor: pointer
		border-radius: 6px
		padding: 12px
		border-radius: 6px
		border: 1px solid #ced4da
		min-height: 96px
		align-items: flex-start
		padding: 8px
		text-decoration: none
		color: var(--pretalx-clr-primary-text)
		@media (hover: hover)
			&:hover
				border-color: var(--pretalx-clr-primary)

		.inner-card-content
			margin-top: 8px
			margin-left: 8px
			p
				color: var(--pretalx-clr-text)
				font-size: 14px

		.img-wrapper
			width: 100px
			height: 100px
			img, .avatar-placeholder
				width: 100px
				height: 100px

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
