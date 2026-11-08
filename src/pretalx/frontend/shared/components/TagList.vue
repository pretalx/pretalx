<!--
SPDX-FileCopyrightText: 2026-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
.c-tag-list(ref="list", :class="{measuring}")
	span.tag(v-for="(tag, index) in tags", v-show="measuring || index < visibleCount", :key="tag.id", ref="tagElements", :title="tag.name")
		span.dot(:style="{'background-color': tag.color}")
		span.name {{ tag.name }}
	span.overflow(v-show="measuring || hiddenTags.length", ref="overflow", :title="hiddenTagNames", aria-hidden="true") +{{ measuring ? tags.length : hiddenTags.length }}
	span.visually-hidden(v-if="hiddenTags.length") {{ hiddenTagNames }}
</template>
<script>
export default {
	props: {
		tags: {
			type: Array,
			default: () => []
		}
	},
	data () {
		return {
			measuring: true,
			visibleCount: this.tags.length
		}
	},
	computed: {
		hiddenTags () {
			return this.tags.slice(this.visibleCount)
		},
		hiddenTagNames () {
			return this.hiddenTags.map(tag => tag.name).join(', ')
		}
	},
	watch: {
		tags () {
			this.fit()
		}
	},
	mounted () {
		this.observer = new ResizeObserver(() => this.fit())
		this.observer.observe(this.$refs.list)
	},
	beforeUnmount () {
		this.observer.disconnect()
	},
	methods: {
		async fit () {
			this.measuring = true
			await this.$nextTick()
			const list = this.$refs.list
			if (!list) return
			const available = list.getBoundingClientRect().width
			const gap = parseFloat(getComputedStyle(list).columnGap) || 0
			const widths = (this.$refs.tagElements || []).map(element => element.getBoundingClientRect().width)
			const overflowWidth = this.$refs.overflow.getBoundingClientRect().width
			const ends = []
			for (const width of widths) ends.push((ends.length ? ends.at(-1) + gap : 0) + width)
			let visible = ends.filter(end => end <= available).length
			if (visible < widths.length) {
				while (visible > 0 && ends[visible - 1] + gap + overflowWidth > available) visible--
				visible = Math.max(visible, 1)
			}
			this.visibleCount = visible
			this.measuring = false
		}
	}
}
</script>
<style lang="stylus">
.c-tag-list
	display: flex
	flex-wrap: nowrap
	gap: 12px
	min-width: 0
	overflow: hidden
	font-size: 13px
	line-height: 18px
	position: relative
	color: $clr-secondary-text-light
	.tag
		display: inline-flex
		align-items: center
		gap: 4px
		min-width: 0
	.dot
		flex: none
		width: 8px
		height: 8px
		border-radius: 50%
	.name
		overflow: hidden
		text-overflow: ellipsis
		white-space: nowrap
	.overflow
		flex: none
		font-weight: 600
	.visually-hidden
		position: absolute
		width: 1px
		height: 1px
		padding: 0
		margin: -1px
		overflow: hidden
		clip-path: inset(50%)
		white-space: nowrap
	&.measuring
		.tag
			flex: none
</style>
