// SPDX-FileCopyrightText: 2022-present NONE
// SPDX-License-Identifier: CC0-1.0

import vue from 'eslint-plugin-vue'
import vuePug from 'eslint-plugin-vue-pug'
import stylistic from '@stylistic/eslint-plugin'

export default [
	...vue.configs['flat/recommended'],
	...vuePug.configs['flat/recommended'],
	{
		ignores: ['dist/**', 'node_modules/**'],
	},
	{
		languageOptions: {
			ecmaVersion: 'latest',
			sourceType: 'module',
		},
		plugins: {
			'@stylistic': stylistic,
		},
		rules: {
			'@stylistic/indent': ['error', 'tab', {SwitchCase: 1}],
			curly: 'off',
			'no-return-assign': 'off',
			'vue/require-default-prop': 'off',
			'vue/multi-word-component-names': 'off',
			'vue/max-attributes-per-line': 'off',
			'vue/attribute-hyphenation': ['warn', 'never'],
			'vue/v-on-event-hyphenation': ['warn', 'never'],
			'vue/no-v-html': 'off',
			'vue/require-v-for-key': 'warn',
			'vue/valid-v-for': 'warn',
		},
	},
]
