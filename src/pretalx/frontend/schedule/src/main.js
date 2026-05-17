// SPDX-FileCopyrightText: 2020-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// Same-origin mount of the public schedule, embedded into Django-rendered
// pages via the {% vite_asset %} template tag. The component is mounted onto
// the server-rendered #pretalx-schedule element and takes its props from
// that element's data-* attributes (event-url, version, locale, timezone,
// format, …). The standalone dev harness (index.html) provides the same
// element with demo data. The web component build uses main-wc.js instead.
import { createApp } from 'vue'
import Buntpapier from 'buntpapier'
import App from '~/App.vue'
import '~/styles/global.styl'

const el = document.querySelector('#pretalx-schedule')
if (el) {
	createApp(App, { ...el.dataset }).use(Buntpapier).mount(el)
}
