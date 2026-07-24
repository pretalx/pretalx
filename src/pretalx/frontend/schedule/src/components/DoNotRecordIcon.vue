<!--
SPDX-FileCopyrightText: 2026-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
svg.do-not-record(viewBox="0 0 116.59076 116.59076", fill="none", xmlns="http://www.w3.org/2000/svg", role="img", :aria-label="translationMessages?.not_recorded || 'Not recorded'")
	g(transform="translate(-9.3465481,-5.441411)")
		rect(style="fill:#000000;fill-opacity;stroke:none;stroke-width:11.2589;stroke-linecap:round;stroke-dasharray:none;stroke-opacity:1;paint-order:markers stroke fill", width="52.753284", height="39.619537", x="35.496307", y="43.927021", rx="5.5179553", ry="7.573648")
		path(style="fill:#000000;fill-opacity:1;stroke:none;stroke-width:18.7997;stroke-linecap:round;stroke-dasharray:none;stroke-opacity:1;paint-order:markers stroke fill", d="M 99.787546,47.04792 V 80.425654 L 77.727407,63.736793 Z")
		path(style="fill:none;stroke:#b23e65;stroke-width:12;stroke-linecap:round;stroke-dasharray:none;stroke-opacity:1;paint-order:markers stroke fill", d="m 35.553146,95.825578 64.177559,-64.17757 m 16.294055,32.08879 A 48.382828,48.382828 0 0 1 67.641925,112.11961 48.382828,48.382828 0 0 1 19.259099,63.736798 48.382828,48.382828 0 0 1 67.641925,15.353968 48.382828,48.382828 0 0 1 116.02476,63.736798 Z")
</template>

<script>
export default {
	name: 'DoNotRecordIcon',
	inject: {
		translationMessages: { default: () => ({}) }
	}
}
</script>
