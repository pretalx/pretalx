<!--
SPDX-FileCopyrightText: 2020-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
transition(name="jump-to-now")
	.c-jump-to-now(v-if="visible")
		button.jump-button(@click="$emit('jump')")
			svg(viewBox="0 0 24 24", fill="currentColor")
				path(d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67V7z")
			span {{ label }}
		button.dismiss-button(@click="$emit('dismiss')", :aria-label="translationMessages.dismiss || 'Dismiss'")
			svg(viewBox="0 0 24 24", fill="currentColor")
				path(d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z")
</template>
<script>
export default {
	name: 'JumpToNow',
	inject: {
		translationMessages: { default: () => ({}) }
	},
	props: {
		visible: {
			type: Boolean,
			default: true
		},
		label: {
			type: String,
			default: 'Jump to now'
		}
	},
	emits: ['jump', 'dismiss']
}
</script>
<style lang="stylus">
.c-jump-to-now
	position: fixed
	bottom: 36px
	right: 20px
	z-index: 100
	display: flex
	align-items: center
	gap: 4px
	background-color: var(--pretalx-clr-primary, #3aa57c)
	border-radius: 24px
	box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25)
	padding: 4px

	.jump-button
		display: flex
		align-items: center
		gap: 8px
		padding: 8px 16px 8px 12px
		background: none
		border: none
		color: white
		font-size: 14px
		font-weight: 500
		cursor: pointer
		border-radius: 20px
		transition: background-color 0.15s ease

		&:hover
			background-color: rgba(255, 255, 255, 0.15)

		svg
			width: 20px
			height: 20px
			flex-shrink: 0

	.dismiss-button
		display: flex
		align-items: center
		justify-content: center
		width: 28px
		height: 28px
		padding: 0
		background: rgba(255, 255, 255, 0.2)
		border: none
		border-radius: 50%
		color: white
		cursor: pointer
		transition: background-color 0.15s ease

		&:hover
			background-color: rgba(255, 255, 255, 0.35)

		svg
			width: 16px
			height: 16px

// Transition animation
.jump-to-now-enter-active,
.jump-to-now-leave-active
	transition: all 0.2s ease

.jump-to-now-enter-from,
.jump-to-now-leave-to
	opacity: 0
	transform: translateY(20px)
</style>
