<!--
SPDX-FileCopyrightText: 2026-present Tobias Kunze
SPDX-License-Identifier: Apache-2.0
-->

<template lang="pug">
.c-answer-list.answers(v-if="iconAnswers.length > 0 || shortAnswers.length > 0")
	.icon-group(v-if="iconAnswers.length > 0")
		.icon-link(v-for="answer in iconAnswers", :key="answer.id")
			a(:href="answer.answer", target="_blank", rel="noopener noreferrer")
				img(v-if="answer.question.icon?.length && answer.question.icon !== '-' && remoteApiUrl", :src="`${remoteApiUrl}questions/${answer.question.id}/icon/`", :alt="getLocalizedString(answer.question.question)", width="16", height="16")
				span(v-else) {{ getLocalizedString(answer.question.question) }}
	.inline-answer(v-for="answer in shortAnswers", :key="answer.id")
		template(v-if="answer.question.variant === 'url' && answer.answer")
			strong.question
				a(:href="answer.answer", target="_blank", rel="noopener noreferrer") {{ getLocalizedString(answer.question.question) }}
		template(v-else)
			span.question
				strong {{ getLocalizedString(answer.question.question) }}:
			span.answer(v-if="answer.question.variant === 'file'")
				i.fa.fa-file-o
				a(v-if="answer.answer_file", :href="answer.answer_file") {{ fileName(answer.answer_file) }}
				span(v-else) {{ translationMessages.no_file_provided || 'No file provided' }}
			span.answer(v-else-if="answer.question.variant === 'boolean'") {{ answer.answer === 'True' ? (translationMessages.answer_yes || 'Yes') : (translationMessages.answer_no || 'No') }}
			span.answer(v-else-if="answer.answer", v-html="renderMarkdown(answer.answer)")
			span.answer(v-else) {{ translationMessages.no_response || 'No response' }}
</template>

<script>
import { renderMarkdown } from '~/utils'
import localize from '~/mixins/localize'

export default {
	name: 'AnswerList',
	mixins: [localize],
	inject: {
		remoteApiUrl: { default: '' },
		translationMessages: { default: () => ({}) },
		eventUrl: { default: '' }
	},
	props: {
		iconAnswers: {
			type: Array,
			default: () => []
		},
		shortAnswers: {
			type: Array,
			default: () => []
		}
	},
	methods: {
		renderMarkdown,
		fileName (url) {
			try {
				return decodeURIComponent(new URL(url, this.eventUrl).pathname.split('/').pop()) || url
			} catch { return url }
		}
	}
}
</script>

<style lang="stylus">
.c-answer-list
	.icon-group
		display: flex
		flex-wrap: wrap
		gap: 8px
		margin-top: 2px
		margin-bottom: 0

		.icon-link
			display: inline-flex
			align-items: center
			margin-right: 8px
			&:last-child
				margin-right: 0

			a
				display: flex
				align-items: center
				text-decoration: none
				color: var(--pretalx-clr-primary-text)
				&:hover
					text-decoration: underline

				img
					margin-right: 4px

	.inline-answer
		display: block
		margin-bottom: 8px

		.question
			color: var(--pretalx-clr-text)
			margin-right: 4px
			strong
				font-weight: 600

		.answer
			color: var(--pretalx-clr-text)

			p
				margin: 0
				display: inline

			.fa
				margin-right: 4px

			a
				color: var(--pretalx-clr-primary-text)
</style>
