<!--
SPDX-FileCopyrightText: 2020-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
button.filter-pill(:class="{ active, 'has-color': !!color }", :style="pillStyle", @click="$emit('click', $event)")
	slot(name="icon")
	span.label {{ label }}
	span.count(v-if="count !== undefined && count !== null") {{ count }}
</template>

<script>
export default {
	name: 'FilterPill',
	props: {
		label: {
			type: String,
			required: true
		},
		count: {
			type: Number,
			default: undefined
		},
		active: {
			type: Boolean,
			default: false
		},
		color: {
			type: String,
			default: null
		}
	},
	emits: ['click'],
	computed: {
		pillStyle () {
			if (!this.color) return {}
			return {
				'--pill-color': this.color
			}
		}
	}
}
</script>

<style lang="stylus">
.pretalx-schedule .filter-pill
	display: inline-flex
	align-items: center
	gap: 4px
	padding: 6px 12px
	border-radius: 16px
	font-size: 14px
	font-weight: 500
	cursor: pointer
	transition: border-color 0.2s ease, background-color 0.2s ease, color 0.2s ease, opacity 0.2s ease
	border: 1.5px solid var(--pretalx-clr-border)
	background-color: transparent
	color: var(--color-grey-dark, #495057)
	white-space: nowrap

	@media (prefers-reduced-motion: reduce)
		transition: none

	@media (hover: hover)
		&:hover
			// Hover border stays more prominent than the resting --color-border in
			// both schemes: #6c757d is darker than #ced4da, #adb5bd lighter than #495057.
			border-color: var(--color-grey-medium, #6c757d)
			background-color: var(--color-grey-lightest, #f8f9fa)

	&.active
		border-color: var(--pill-color, var(--pretalx-clr-primary))
		background-color: var(--pill-color, var(--pretalx-clr-primary))
		// Colourless pills fall back to the brand fill, whose ink event_css may
		// override; coloured pills carry a fixed track/tag colour instead.
		color: var(--pretalx-clr-text-on-primary)

		&.has-color
			color: var(--pretalx-clr-text-on-fill)

		@media (hover: hover)
			&:hover
				opacity: 0.9

	&.has-color
		// Declared here, not in tokens.styl: --pill-color is set inline per pill,
		// so a declaration on html/body would substitute an absent --pill-color.
		--pretalx-clr-pill-ink: var(--pill-color)

		&:not(.active)
			border-color: var(--pretalx-clr-pill-ink)
			color: var(--pretalx-clr-pill-ink)

			@media (hover: hover)
				&:hover
					background-color: var(--pill-color)
					color: var(--pretalx-clr-text-on-fill)
					opacity: 0.85

	@media (prefers-color-scheme: dark)
		// Track/tag colours are authored against a white schedule, so dark hues are
		// common; lift them for use as ink on #121416. Fills keep the raw colour.
		&.has-color
			--pretalx-clr-pill-ink: unquote('color-mix(in srgb, var(--pill-color), white 45%)')

	.label
		line-height: 1.2

	.count
		font-weight: 600
</style>
