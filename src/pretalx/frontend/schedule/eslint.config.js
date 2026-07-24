// SPDX-FileCopyrightText: 2020-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

import pluginVue from 'eslint-plugin-vue'
import vuePug from 'eslint-plugin-vue-pug'

export default [
	...pluginVue.configs['flat/recommended'],
	...vuePug.configs['flat/recommended'],
	{
		rules: {
			'indent': ['error', 'tab', { SwitchCase: 1 }],
			'no-tabs': 'off',
			'comma-dangle': 'off',
			'curly': 'off',
			'no-return-assign': 'off',
			'vue/require-default-prop': 'off',
			'vue/multi-word-component-names': 'off',
			'vue/html-indent': ['error', 'tab'],
			'vue/max-attributes-per-line': 'off',
			'vue/attribute-hyphenation': ['warn', 'never'],
			'vue/v-on-event-hyphenation': ['warn', 'never'],
			'vue/no-v-html': 'off',
			'vue/no-lone-template': 'error',
		}
	}
]
