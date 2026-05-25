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
	transition: all 0.2s ease
	border: 1.5px solid $clr-grey-300
	background-color: transparent
	color: $clr-grey-700
	white-space: nowrap

	&:hover
		border-color: $clr-grey-400
		background-color: $clr-grey-100
		color: $clr-grey-700

	&.active
		border-color: var(--pill-color, var(--pretalx-clr-primary))
		background-color: var(--pill-color, var(--pretalx-clr-primary))
		color: $clr-white

		&:hover
			background-color: var(--pill-color, var(--pretalx-clr-primary))
			color: $clr-white
			opacity: 0.9

	&.has-color:not(.active)
		border-color: var(--pill-color)
		color: var(--pill-color)

		&:hover
			background-color: var(--pill-color)
			color: $clr-white
			opacity: 0.85

	.label
		line-height: 1.2

	.count
		font-weight: 600
</style>
