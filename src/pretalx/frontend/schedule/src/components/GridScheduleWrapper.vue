<!--
SPDX-FileCopyrightText: 2020-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
.c-grid-schedule-wrapper
	grid-schedule(
		v-for="(group, index) in gridGroups",
		:key="group.days.join('-')",
		:ref="'gridSchedule' + index",
		:sessions="group.sessions",
		:rooms="group.rooms",
		:currentDay="currentDay",
		:now="now",
		:hasAmPm="hasAmPm",
		:timezone="timezone",
		:locale="locale",
		:scrollParent="scrollParent",
		:favs="favs",
		:signups="signups",
		:onHomeServer="onHomeServer",
		@changeDay="$emit('changeDay', $event)",
		@fav="$emit('fav', $event)",
		@unfav="$emit('unfav', $event)"
	)
</template>
<script>
import { DateTime } from 'luxon'
import GridSchedule from '~/components/GridSchedule'

export default {
	components: { GridSchedule },
	props: {
		sessions: Array,
		rooms: Array,
		favs: {
			type: Array,
			default () {
				return []
			}
		},
		signups: {
			type: Array,
			default () {
				return []
			}
		},
		days: Array,
		currentDay: String,
		now: Object,
		timezone: String,
		locale: String,
		hasAmPm: Boolean,
		scrollParent: Element,
		onHomeServer: Boolean
	},
	computed: {
		gridGroups () {
			/*
				Life was fine and we only had a single big grid for the grid schedule, and then ~~the Fire Nation attacked~~
				we had some conferences that e.g. had only workshops on the first day, but had the workshop rooms all the way to the
				right to keep the main program front and center. The first day would look near-empty and require side-scrolling to
				see the workshop rooms.
				So now we’re grouping days in order to avoid this problem. gridGroups contain one or multiple consecutive days and
				will show the same rooms across those days.
			*/

			// First pass: create groups of one day and put all sessions into their day(s)
			const dayToSessions = new Map();
			for (const session of this.sessions) {
				const startDay = session.start.setZone(this.timezone).startOf('day');
				const endDay = session.end.setZone(this.timezone).startOf('day');
				for (let day = startDay; day <= endDay; day = day.plus({days: 1})) {
					const dayKey = day.toISODate();
					if (!dayToSessions.has(dayKey)) {
						dayToSessions.set(dayKey, []);
					}
					dayToSessions.get(dayKey).push(session);
				}
			}

			const initialGroups = Array.from(dayToSessions.keys()).map((day) => ({
				days: [day],
				sessions: new Set(dayToSessions.get(day)),
				rooms: new Set(dayToSessions.get(day).map((session) => session.room)),
			}));

			// Second pass: merge consecutive groups if they share sessions or their set of rooms is exactly the same
			const mergedGroups = [];
			for (const group of initialGroups) {
				const lastGroup = mergedGroups[mergedGroups.length - 1];
				if (!lastGroup) {
					mergedGroups.push(group);
					continue;
				}
				const hasSharedSessions = group.sessions.intersection(lastGroup.sessions).size > 0;
				const hasSameRooms = group.rooms.symmetricDifference(lastGroup.rooms).size === 0;
				if (hasSharedSessions || hasSameRooms) {
					lastGroup.days.push(...group.days);
					lastGroup.sessions = new Set([...lastGroup.sessions, ...group.sessions]);
					lastGroup.rooms = new Set([...lastGroup.rooms, ...group.rooms]);
				} else {
					mergedGroups.push(group);
				}
			}

			// Final pass: sort rooms by original order
			for (const group of mergedGroups) {
				group.rooms = this.rooms.filter((room) => group.rooms.has(room));
				group.sessions = Array.from(group.sessions);
			}
			return mergedGroups
		}
	},
	methods: {
		changeDay (day) {
			// Call changeDay on all GridSchedule children using refs
			for (let i = 0; i < this.gridGroups.length; i++) {
				const childRef = this.$refs['gridSchedule' + i]
				if (childRef && childRef[0] && childRef[0].changeDay) {
					childRef[0].changeDay(day)
				}
			}
		},
		scrollToNow () {
			// Find the GridSchedule that has "now" and scroll to it
			for (let i = 0; i < this.gridGroups.length; i++) {
				const childRef = this.$refs['gridSchedule' + i]
				if (childRef && childRef[0] && childRef[0].nowSlice) {
					childRef[0].scrollToNow()
					return
				}
			}
		}
	}
}
</script>
