// SPDX-FileCopyrightText: 2020-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

import pluginVue from 'eslint-plugin-vue'

export default [
	...pluginVue.configs['flat/recommended'],
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
		}
	}
]
