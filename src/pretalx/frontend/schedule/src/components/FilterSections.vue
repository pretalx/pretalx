<!--
SPDX-FileCopyrightText: 2020-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
.filter-sections
	.filter-section(v-if="tracks.length > 1")
		label.section-label {{ translationMessages.tracks || 'Tracks' }}
		.pills-container
			filter-pill(
				v-for="track in tracks",
				:key="track.id",
				:label="getLocalizedString(track.name)",
				:active="selectedTrackIds.includes(track.id)",
				:color="track.color",
				@click="$emit('toggleTrack', track.id)"
			)

	.filter-section(v-if="languages.length > 1")
		label.section-label {{ translationMessages.languages || 'Languages' }}
		.pills-container
			filter-pill(
				v-for="language in languages",
				:key="language",
				:label="getLanguageName(language)",
				:active="selectedLanguageCodes.includes(language)",
				@click="$emit('toggleLanguage', language)"
			)

	.filter-section(v-if="tags && tags.length > 0")
		label.section-label {{ translationMessages.tags || 'Tags' }}
		.pills-container
			filter-pill(
				v-for="tag in tags",
				:key="tag.id",
				:label="getLocalizedString(tag.name)",
				:active="selectedTagIds.includes(tag.id)",
				:color="tag.color",
				@click="$emit('toggleTag', tag.id)"
			)

	.filter-section(v-if="hasNonRecordedSessions")
		label.section-label {{ translationMessages.recording || 'Recording' }}
		.pills-container
			filter-pill(
				:label="translationMessages.not_recorded || 'Not recorded'",
				:active="filterDoNotRecord",
				@click="$emit('toggleDoNotRecord')"
			)

	.filter-section(v-if="hasSignupSessions")
		label.section-label {{ translationMessages.signup_section || 'Signup' }}
		.pills-container
			filter-pill(
				:label="translationMessages.signup_only || 'Only sessions requiring signup'",
				:active="onlyRequiresSignup",
				@click="$emit('toggleRequiresSignup')"
			)
				template(#icon)
					i.fa.fa-user-plus.signup-icon
			//"Hide full" only shows when filtering by "Only sessions requiring signup"
			filter-pill(
				v-if="hasFullSessions && onlyRequiresSignup",
				:label="translationMessages.signup_hide_full || 'Hide full sessions'",
				:active="onlyWithCapacity",
				@click="$emit('toggleWithCapacity')"
			)

	.filter-section
		label.section-label {{ translationMessages.search || 'Search' }}
		.search-input-wrapper
			svg.search-icon(viewBox="0 0 24 24", fill="none", stroke="currentColor", stroke-width="2")
				circle(cx="11", cy="11", r="8")
				path(d="m21 21-4.35-4.35")
			input.search-input(
				type="text",
				:value="searchQuery",
				@input="$emit('searchInput', $event)",
				ref="searchInput"
			)
</template>

<script>
import localize from '~/mixins/localize'
import FilterPill from '~/components/FilterPill.vue'

export default {
	name: 'FilterSections',
	components: { FilterPill },
	mixins: [localize],
	props: {
		tracks: {
			type: Array,
			default: () => []
		},
		selectedTrackIds: {
			type: Array,
			default: () => []
		},
		languages: {
			type: Array,
			default: () => []
		},
		selectedLanguageCodes: {
			type: Array,
			default: () => []
		},
		tags: {
			type: Array,
			default: () => []
		},
		selectedTagIds: {
			type: Array,
			default: () => []
		},
		hasNonRecordedSessions: {
			type: Boolean,
			default: false
		},
		filterDoNotRecord: {
			type: Boolean,
			default: false
		},
		hasSignupSessions: {
			type: Boolean,
			default: false
		},
		hasFullSessions: {
			type: Boolean,
			default: false
		},
		onlyRequiresSignup: {
			type: Boolean,
			default: false
		},
		onlyWithCapacity: {
			type: Boolean,
			default: false
		},
		searchQuery: {
			type: String,
			default: ''
		},
		translationMessages: {
			type: Object,
			default: () => ({})
		}
	},
	emits: ['toggleTrack', 'toggleLanguage', 'toggleTag', 'toggleDoNotRecord', 'toggleRequiresSignup', 'toggleWithCapacity', 'searchInput'],
	methods: {
		focusSearchInput () {
			this.$refs.searchInput?.focus()
		}
	}
}
</script>

<style lang="stylus">
.filter-sections
	.filter-section
		margin-bottom: 20px

		&:last-child
			margin-bottom: 0

		.section-label
			display: block
			font-size: 13px
			font-weight: 600
			color: $clr-grey-600
			margin-bottom: 8px
			text-transform: uppercase
			letter-spacing: 0.5px

		.pills-container
			display: flex
			flex-wrap: wrap
			gap: 8px

		.search-input-wrapper
			position: relative
			display: flex
			align-items: center

			.search-icon
				position: absolute
				left: 12px
				width: 18px
				height: 18px
				color: $clr-grey-400
				pointer-events: none

			.search-input
				width: 100%
				padding: 10px 14px 10px 38px
				border: 1.5px solid $clr-grey-300
				border-radius: 8px
				font-size: 14px
				outline: none
				transition: border-color 0.2s ease
				box-sizing: border-box

				&:focus
					border-color: var(--pretalx-clr-primary)
</style>
