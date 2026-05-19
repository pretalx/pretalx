<!--
SPDX-FileCopyrightText: 2020-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
.fav-button
	bunt-icon-button.btn-fav-container(@click.prevent.stop="handleClick")
		svg.star(viewBox="0 0 24 24", :class="{'rotate-star': rotating}")
			path(d="M12,17.27L18.18,21L16.54,13.97L22,9.24L14.81,8.62L12,2L9.19,8.62L2,9.24L7.45,13.97L5.82,21L12,17.27Z")
</template>

<script>
export default {
	name: 'FavButton',
	emits: ['toggleFav'],
	data () {
		return {
			rotating: false
		}
	},
	methods: {
		handleClick () {
			this.$emit('toggleFav')
			this.rotating = true
			setTimeout(() => {
				this.rotating = false
			}, 400)
		}
	}
}
</script>

<style lang="stylus">
svg.star
	height: 20px
	width: 20px
	path
		fill: none
		stroke: #ffa000
		stroke-width: 1px
		vector-effect: non-scaling-stroke
	&.rotate-star
		animation: rotate-star 0.4s
.faved
	svg.star
		filter: drop-shadow(0 0 1px rgba(0 0 0 0.17))
		path
			fill: #ffa000
@keyframes rotate-star
	0%
		transform: rotate(0deg)
	100%
		transform: rotate(72deg)
</style>
