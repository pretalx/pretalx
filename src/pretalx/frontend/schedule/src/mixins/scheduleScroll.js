// SPDX-FileCopyrightText: 2020-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

import { DateTime } from 'luxon'

export default {
	data() {
		return {
			observer: null,
			programmaticScroll: false
		}
	},

	watch: {
		timezone() {
			// Rebuild intersection observer when timezone changes
			this.$nextTick(() => {
				this.setupIntersectionObserver()
			})
		}
	},

	methods: {
		setupIntersectionObserver() {
			// Disconnect existing observer if it exists
			if (this.observer) {
				this.observer.disconnect()
			}

			// Create new intersection observer
			this.observer = new IntersectionObserver(this.onIntersect, {
				root: this.scrollParent,
				rootMargin: '-45% 0px'
			})

			// Call component-specific observe method
			this.observeElements()
		},

		onIntersect(results) {
			// Skip if we're doing programmatic scroll to avoid interference with tab clicks
			if (this.programmaticScroll) return

			const intersection = results[0]
			if (!intersection) return

			// Parse the date with the correct timezone context
			const originalDate = DateTime.fromISO(intersection.target.dataset.date || intersection.target.dataset.slice, { zone: this.timezone })
			// Preserve the calendar date when converting timezones for day boundaries
			const day = DateTime.fromObject({
				year: originalDate.year,
				month: originalDate.month,
				day: originalDate.day
			}, { zone: this.timezone })

			if (intersection.isIntersecting) {
				this.$emit('changeDay', day)
			} else if (intersection.rootBounds && (intersection.boundingClientRect.y - intersection.rootBounds.y) > 0) {
				this.$emit('changeDay', day.minus({days: 1}))
			}
		},

		programmaticScrollTo(element) {
			if (!element) return

			// Temporarily disable intersection observer during programmatic scroll
			this.programmaticScroll = true

			const scrollTop = this.calculateScrollTop(element)
			if (this.scrollParent) {
				this.scrollParent.scrollTo({ top: scrollTop, behavior: 'smooth' })
			} else {
				window.scroll({ top: scrollTop, behavior: 'smooth' })
			}

			// Re-enable intersection observer after scroll completes
			setTimeout(() => {
				this.programmaticScroll = false
			}, 500)
		}
	}
}
