<!--
SPDX-FileCopyrightText: 2020-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
.filter-bar(:class="{ 'two-rows': isMobile && hasActiveFilters }")
	//- Left side: All filter controls grouped together
	.filter-controls
		//- Favorites pill - toggles directly
		filter-pill.fav-pill(
			v-if="favsCount > 0 || onlyFavs",
			:label="favsCount.toString()",
			:active="onlyFavs",
			color="#FFA000",
			@click="$emit('toggleFavs')",
			:aria-label="translationMessages.toggle_favs || 'Toggle favourites filter'"
		)
			template(#icon)
				svg.star-icon(viewBox="0 0 24 24")
					polygon(points="14.43,10 12,2 9.57,10 2,10 8.18,14.41 5.83,22 12,17.31 18.18,22 15.83,14.41 22,10")

		filter-pill.signed-up-pill(
			v-if="signupsCount > 0 || onlySignedUp",
			:label="signupsCount.toString()",
			:active="onlySignedUp",
			color="var(--pretalx-clr-success)",
			@click="$emit('toggleSignedUp')",
			:aria-label="translationMessages.toggle_signups || 'Toggle signed-up filter'"
		)
			template(#icon)
				i.fa.fa-calendar-check-o.signed-up-icon

		//- Active filter pills (max 2 shown, read-only - click opens sheet)
		template(v-for="(pill, index) in visibleFilterPills", :key="pill.key")
			filter-pill(
				:label="pill.label",
				:active="true",
				:color="pill.color",
				@click="$emit('openFilter')"
			)

		//- "+N more" pill if >2 filters active
		filter-pill.more-pill(
			v-if="hiddenFilterCount > 0",
			:label="'+' + hiddenFilterCount + ' more'",
			:active="true",
			@click="$emit('openFilter')"
		)

		filter-pill.filter-trigger.clear-all-trigger(
			v-if="hasActiveFilters",
			:label="translationMessages.clear_filters || 'Clear filters'",
			@click="$emit('clearAll')",
			:aria-label="translationMessages.clear_filters || 'Clear filters'"
		)
			template(#icon)
				svg.filter-icon(viewBox="0 0 24 24", fill="currentColor")
					path(d="M3 4a1 1 0 0 1 1-1h16a1 1 0 0 1 .78 1.625l-6.28 7.85V18a1 1 0 0 1-.553.894l-4 2A1 1 0 0 1 8.5 20v-7.525L2.22 4.625A1 1 0 0 1 3 4z")
		filter-pill.filter-trigger(
			v-else,
			:label="translationMessages.filter || 'Filter'",
			@click="$emit('openFilter')",
			:aria-label="translationMessages.filter || 'Filter'"
		)
			template(#icon)
				svg.filter-icon(viewBox="0 0 24 24", fill="currentColor")
					path(d="M3 4a1 1 0 0 1 1-1h16a1 1 0 0 1 .78 1.625l-6.28 7.85V18a1 1 0 0 1-.553.894l-4 2A1 1 0 0 1 8.5 20v-7.525L2.22 4.625A1 1 0 0 1 3 4z")


	//- Right side: Timezone selector only
	.timezone-container
		template(v-if="!inEventTimezone")
			//- dropdown-class: the dropdown menu is teleported to #bunt-teleport-target
			//- (a sibling of .filter-bar), so a descendant selector cannot reach it.
			bunt-select.timezone-select(name="timezone", dropdown-class="timezone-dropdown", :options="timezoneOptions", v-model="timezoneModel", @blur="$emit('saveTimezone')")
		template(v-else-if="scheduleTimezone")
			.timezone-label {{ scheduleTimezone }}
</template>

<script>
import localize from '~/mixins/localize'
import FilterPill from '~/components/FilterPill.vue'

export default {
	name: 'FilterBar',
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
		filterDoNotRecord: {
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
		favsCount: {
			type: Number,
			default: 0
		},
		onlyFavs: {
			type: Boolean,
			default: false
		},
		signupsCount: {
			type: Number,
			default: 0
		},
		onlySignedUp: {
			type: Boolean,
			default: false
		},
		inEventTimezone: {
			type: Boolean,
			default: true
		},
		currentTimezone: String,
		scheduleTimezone: String,
		userTimezone: String,
		isMobile: {
			type: Boolean,
			default: false
		},
		translationMessages: {
			type: Object,
			default: () => ({})
		}
	},
	emits: ['openFilter', 'toggleFavs', 'toggleSignedUp', 'saveTimezone', 'update:currentTimezone', 'clearAll'],
	computed: {
		filterPills () {
			const pills = []

			for (const trackId of this.selectedTrackIds) {
				const track = this.tracks.find(t => t.id === trackId)
				if (track) {
					pills.push({
						key: `track-${trackId}`,
						label: this.getLocalizedString(track.name),
						color: track.color
					})
				}
			}

			for (const code of this.selectedLanguageCodes) {
				pills.push({
					key: `lang-${code}`,
					label: this.getLanguageName(code),
					color: null
				})
			}

			if (this.filterDoNotRecord) {
				pills.push({
					key: 'do-not-record',
					label: this.translationMessages.not_recorded || 'Not recorded',
					color: null
				})
			}

			if (this.onlyRequiresSignup) {
				pills.push({
					key: 'requires-signup',
					label: this.translationMessages.signup_only || 'Only sessions requiring signup',
					color: null
				})
			}

			if (this.onlyWithCapacity) {
				pills.push({
					key: 'hide-full',
					label: this.translationMessages.signup_hide_full || 'Hide full sessions',
					color: null
				})
			}

			if (this.searchQuery) {
				pills.push({
					key: 'search',
					label: `"${this.searchQuery}"`,
					color: null
				})
			}

			return pills
		},
		visibleFilterPills () {
			return this.filterPills.slice(0, 2)
		},
		hiddenFilterCount () {
			return Math.max(0, this.filterPills.length - 2)
		},
		hasActiveFilters () {
			return this.filterPills.length > 0
		},
		timezoneOptions () {
			return [
				{ id: this.scheduleTimezone, label: this.scheduleTimezone },
				{ id: this.userTimezone, label: this.userTimezone }
			]
		},
		timezoneModel: {
			get () {
				return this.currentTimezone
			},
			set (value) {
				this.$emit('update:currentTimezone', value)
			}
		}
	}
}
</script>

<style lang="stylus">
.filter-bar
	display: flex
	align-items: center
	justify-content: space-between
	padding: 8px 0
	gap: 12px
	width: 100%
	max-width: var(--schedule-max-width)
	align-self: center
	background-color: var(--color-bg)

	&.two-rows
		flex-direction: column-reverse
		align-items: stretch
		gap: 8px

		.filter-controls
			align-self: flex-start

		.timezone-container
			align-self: flex-end
			margin-left: 0

	.filter-controls
		display: flex
		align-items: center
		gap: 8px
		padding-left: 8px
		flex-wrap: wrap
		min-width: 0

		.fav-pill
			.star-icon
				width: 16px
				height: 16px
				fill: currentColor

		.signed-up-pill
			.signed-up-icon
				font-size: 14px

	.timezone-container
		display: flex
		align-items: center
		flex-shrink: 0
		margin-left: auto
		padding-right: 8px

		.timezone-select
			max-width: 200px

			// buntpapier emits select()/input() unconditionally and this app never
			// calls select-style(style: 'dark'), so these inks are hardcoded light.
			// Scoped to .timezone-container so other bunt-selects are unaffected.
			.open-indicator
				color: var(--color-text-lighter)

			.bunt-input
				input
					color: var(--color-text-input)

				// input() strokes the outline with a 38%-black that vanishes on #121416.
				.outline
					stroke: var(--pretalx-clr-subtle-ink)

		.timezone-label
			color: var(--color-text-lighter)
			font-size: 14px
			white-space: nowrap

	.filter-trigger
		flex-shrink: 0

		&.clear-all-trigger
			border-color: var(--color-danger)
			background-color: transparent
			color: var(--color-danger-text)

			@media (hover: hover)
				&:hover
					border-color: var(--color-danger)
					background-color: var(--color-danger)
					// Ink on a hue-fixed rose fill that does not follow the
					// scheme, so it must stay scheme-independent.
					color: var(--pretalx-clr-text-on-fill)

		.filter-icon
			width: 18px
			height: 18px
			fill: currentColor

// The timezone dropdown is teleported to #bunt-teleport-target, a sibling of
// .filter-bar, so it cannot be nested in the block above. buntpapier styles it
// with card(), which hardcodes background-color: $clr-white and emits no colour,
// leaving near-white ink on a white card in dark mode. The .timezone-dropdown
// class (passed via the dropdown-class prop) keeps this off other bunt-selects.
.bunt-select-dropdown-menu.timezone-dropdown
	background-color: var(--color-bg)
	color: var(--color-text)
	border: 1px solid var(--color-border)
	// card() is shadow-only and select.styl removes the top border so the menu
	// reads as attached to the input; keep that while adding an edge for dark.
	border-top: none

	li.highlight
		// $highlight-color falls through to buntpapier's $clr-blue, which is never
		// overridden here; var(--color-grey-lightest) flips with the card surface.
		background-color: var(--color-grey-lightest)
</style>
