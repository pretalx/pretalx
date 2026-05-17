// SPDX-FileCopyrightText: 2020-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

import { createApp, defineCustomElement } from 'vue'
import Buntpapier from 'buntpapier'
import App from '~/App.vue'

const PretalxSchedule = defineCustomElement(App, {
	configureApp(app) {
		app.use(Buntpapier)
	}
})
customElements.define('pretalx-schedule', PretalxSchedule)
