<!--
SPDX-FileCopyrightText: 2020-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
//- Mobile bottom sheet
Teleport(:to="teleportTarget", v-if="isMobile")
	Transition(name="bottom-sheet-backdrop")
		.filter-bottom-sheet-backdrop(v-if="isOpen", @click="close")
	Transition(name="bottom-sheet")
		.filter-bottom-sheet(v-if="isOpen", role="dialog", aria-modal="true", aria-labelledby="filter-bottom-sheet-heading", @click.stop)
			.sheet-header
				h3#filter-bottom-sheet-heading {{ translationMessages.filters || 'Filters' }}
				button.close-button(@click="close", :aria-label="translationMessages.close_filters || 'Close filters'") ✕

			.sheet-content
				filter-sections(v-bind="filterSectionsProps", v-on="filterSectionsListeners")

			.sheet-footer
				button.show-results-button(@click="applyAndClose") {{ translationMessages.show_results || 'Show results' }}
				button.clear-all-button(v-if="hasActiveFilters", @click="clearAll") {{ translationMessages.clear_filters || 'Clear filters' }}

//- Desktop dialog
dialog.pretalx-modal#filter-bottom-sheet-dialog(v-if="!isMobile", ref="modal", @click.stop="close")
	.dialog-inner(@click.stop)
		button.close-button(@click="close") ✕
		.dialog-header
			h3 {{ translationMessages.filters || 'Filters' }}

		filter-sections(v-bind="filterSectionsProps", v-on="filterSectionsListeners")

		.dialog-footer
			button.show-results-button(@click="applyAndClose") {{ translationMessages.show_results || 'Show results' }}
			button.clear-all-button(v-if="hasActiveFilters", @click="clearAll") {{ translationMessages.clear_filters || 'Clear filters' }}
</template>

<script>
import { Teleport, Transition } from 'vue'
import FilterSections from '~/components/FilterSections.vue'

export default {
	name: 'FilterBottomSheet',
	components: { FilterSections, Teleport, Transition },
	inject: {
		buntTeleportTarget: { default: null }
	},
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
		isMobile: {
			type: Boolean,
			default: false
		},
		translationMessages: {
			type: Object,
			default: () => ({})
		}
	},
	emits: ['trackToggled', 'languageToggled', 'tagToggled', 'doNotRecordToggled', 'requiresSignupToggled', 'withCapacityToggled', 'searchQueryChange', 'clearAll', 'close'],
	data () {
		return {
			isOpen: false,
			// Local debounce buffer for the search input only; all other filter
			// state lives in the parent and flows down via props.
			localSearchQuery: this.searchQuery,
			searchDebounceTimer: null
		}
	},
	computed: {
		teleportTarget () {
			return this.buntTeleportTarget || document.body
		},
		filterSectionsProps () {
			return {
				tracks: this.tracks,
				selectedTrackIds: this.selectedTrackIds,
				languages: this.languages,
				selectedLanguageCodes: this.selectedLanguageCodes,
				tags: this.tags,
				selectedTagIds: this.selectedTagIds,
				hasNonRecordedSessions: this.hasNonRecordedSessions,
				filterDoNotRecord: this.filterDoNotRecord,
				hasSignupSessions: this.hasSignupSessions,
				hasFullSessions: this.hasFullSessions,
				onlyRequiresSignup: this.onlyRequiresSignup,
				onlyWithCapacity: this.onlyWithCapacity,
				searchQuery: this.localSearchQuery,
				translationMessages: this.translationMessages
			}
		},
		filterSectionsListeners () {
			return {
				toggleTrack: (event) => this.$emit('trackToggled', event),
				toggleLanguage: (event) => this.$emit('languageToggled', event),
				toggleTag: (event) => this.$emit('tagToggled', event),
				toggleDoNotRecord: () => this.$emit('doNotRecordToggled'),
				toggleRequiresSignup: () => this.$emit('requiresSignupToggled'),
				toggleWithCapacity: () => this.$emit('withCapacityToggled'),
				searchInput: this.onSearchInput
			}
		},
		hasActiveFilters () {
			return this.selectedTrackIds.length > 0 ||
				this.selectedLanguageCodes.length > 0 ||
				this.selectedTagIds.length > 0 ||
				this.filterDoNotRecord ||
				this.onlyRequiresSignup ||
				this.onlyWithCapacity ||
				this.localSearchQuery.length > 0
		}
	},
	watch: {
		searchQuery: {
			handler (newVal) {
				this.localSearchQuery = newVal
			},
			immediate: true
		},
		isOpen (newVal) {
			if (newVal) {
				document.addEventListener('keydown', this.handleKeydown)
				// Prevent body scroll on mobile
				if (this.isMobile) {
					document.body.style.overflow = 'hidden'
				}
			} else {
				document.removeEventListener('keydown', this.handleKeydown)
				if (this.isMobile) {
					document.body.style.overflow = ''
				}
			}
		}
	},
	beforeUnmount () {
		document.removeEventListener('keydown', this.handleKeydown)
		document.body.style.overflow = ''
		if (this.searchDebounceTimer) {
			clearTimeout(this.searchDebounceTimer)
		}
	},
	methods: {
		showModal () {
			if (this.isMobile) {
				this.isOpen = true
			} else {
				this.$refs.modal?.showModal()
				this.isOpen = true
			}
		},
		close () {
			if (!this.isMobile) {
				this.$refs.modal?.close()
			}
			this.isOpen = false
			this.$emit('close')
		},
		applyAndClose () {
			// Emit any pending search query immediately
			if (this.searchDebounceTimer) {
				clearTimeout(this.searchDebounceTimer)
				this.searchDebounceTimer = null
			}
			if (this.localSearchQuery !== this.searchQuery) {
				this.$emit('searchQueryChange', this.localSearchQuery)
			}
			this.close()
		},
		handleKeydown (event) {
			if (event.key === 'Escape') {
				this.close()
			}
		},
		onSearchInput (event) {
			this.localSearchQuery = event.target.value
			// Debounce search query emission
			if (this.searchDebounceTimer) {
				clearTimeout(this.searchDebounceTimer)
			}
			this.searchDebounceTimer = setTimeout(() => {
				this.$emit('searchQueryChange', this.localSearchQuery)
			}, 300)
		},
		clearAll () {
			if (this.searchDebounceTimer) {
				clearTimeout(this.searchDebounceTimer)
				this.searchDebounceTimer = null
			}
			this.localSearchQuery = ''
			this.$emit('clearAll')
		}
	}
}
</script>

<style lang="stylus">
.pretalx-schedule

	.filter-bottom-sheet-backdrop
		position: fixed
		left: 0
		bottom: 0
		width: 100vw
		height: 100vh
		background-color: rgba(0, 0, 0, 0.5)
		z-index: 999

	.filter-bottom-sheet
		position: fixed
		left: 0
		bottom: 0
		width: 100vw
		max-height: 70vh
		background-color: $clr-white
		border-radius: 16px 16px 0 0
		box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.15)
		z-index: 1000
		display: flex
		flex-direction: column
		overflow: hidden

		.sheet-header
			display: flex
			align-items: center
			justify-content: space-between
			padding: 16px 20px 8px
			border-bottom: 1px solid $clr-grey-200
			flex-shrink: 0
			gap: 12px

			h3
				margin: 0
				font-size: 18px
				font-weight: 600

			.close-button
				background: none
				border: none
				cursor: pointer
				padding: 8px
				color: $clr-grey-600
				font-size: 20px
				font-weight: bold
				line-height: 1
				&:hover
					background: none
					color: $clr-grey-900

		.sheet-content
			flex: 1
			overflow-y: auto
			padding: 16px 20px

		.sheet-footer
			padding: 16px 20px
			border-top: 1px solid $clr-grey-200
			flex-shrink: 0
			display: flex
			flex-direction: column
			gap: 8px

	.show-results-button
		width: 100%
		padding: 12px 20px
		background-color: var(--pretalx-clr-primary)
		color: $clr-white
		border: none
		border-radius: 8px
		font-size: 16px
		font-weight: 600
		cursor: pointer
		transition: opacity 0.2s ease

		&:hover
			background-color: var(--pretalx-clr-primary)
			color: $clr-white
			opacity: 0.9

	.clear-all-button
		width: 100%
		padding: 10px 20px
		background: none
		color: var(--pretalx-clr-primary)
		border: 1px solid var(--pretalx-clr-primary)
		border-radius: 8px
		font-size: 14px
		font-weight: 500
		cursor: pointer
		transition: background-color 0.15s ease, color 0.15s ease

		&:hover
			background-color: var(--pretalx-clr-primary)
			color: $clr-white

	#filter-bottom-sheet-dialog
		position: fixed
		top: 50%
		left: 50%
		right: auto
		margin: 0
		opacity: 0
		transform: translate(-50%, -50%) scale(0.95)
		transition: opacity 0.15s ease, transform 0.15s ease, overlay 0.15s ease allow-discrete, display 0.15s ease allow-discrete

		&[open]
			opacity: 1
			transform: translate(-50%, -50%) scale(1)

		@starting-style
			&[open]
				opacity: 0
				transform: translate(-50%, -50%) scale(0.95)

		&::backdrop
			background-color: rgba(0, 0, 0, 0)
			transition: background-color 0.15s ease, overlay 0.15s ease allow-discrete, display 0.15s ease allow-discrete

		&[open]::backdrop
			background-color: rgba(0, 0, 0, 0.5)

		@starting-style
			&[open]::backdrop
				background-color: rgba(0, 0, 0, 0)

		.dialog-inner
			padding: 16px 24px 20px

		.dialog-header
			display: flex
			align-items: center
			gap: 12px
			margin-bottom: 16px

			h3
				margin: 0
				font-size: 18px
				font-weight: 600

		.dialog-footer
			margin-top: 20px
			padding-top: 16px
			border-top: 1px solid $clr-grey-200
			display: flex
			flex-direction: column
			gap: 8px

// Transitions can't live under .pretalx-schedule because Vue's
// <Transition> components inject outside.
.bottom-sheet-backdrop-enter-active,
.bottom-sheet-backdrop-leave-active
	transition: opacity 0.2s ease

.bottom-sheet-backdrop-enter-from,
.bottom-sheet-backdrop-leave-to
	opacity: 0

.bottom-sheet-enter-active,
.bottom-sheet-leave-active
	transition: transform 0.2s ease-out

.bottom-sheet-enter-from,
.bottom-sheet-leave-to
	transform: translateY(100%)
</style>
