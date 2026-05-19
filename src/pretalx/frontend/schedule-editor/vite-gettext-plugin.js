// SPDX-FileCopyrightText: 2023-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

import { gettextToI18next } from 'i18next-conv'
import {readFileSync} from 'fs'
import {fileURLToPath} from 'url'
import {dirname, resolve} from 'path'

const fileRegex = /locale\/(.*)\/LC_MESSAGES\/django.po$/
// Resolve relative to this plugin file, not the process cwd: the build is
// run from the shared frontend root (../), not from the schedule-editor dir.
const translationsPath = resolve(dirname(fileURLToPath(import.meta.url)), 'locales/en/translation.json')
const relevantKeys = Object.keys(JSON.parse(readFileSync(translationsPath, 'utf8')))

export default function loadGettext () {
	return {
		name: 'load-gettext',
		async transform (src, id) {
			if (fileRegex.test(id)) {
				// Load known keys from ./locales/en/translation.json
				// and use them to replace the keys in the source code
				// with the corresponding values
				const lang = id.match(fileRegex)[1]

				// As per https://github.com/smhg/gettext-parser/issues/79, our
				// frontend doesn't support the #~| syntax, so we need to replace it
				// with #~#|, which is a comment in gettext
				src = src.replaceAll('#~|', '#~#|')

				const mapped = await gettextToI18next(lang, src)
				const mappedJSON = JSON.parse(mapped)
				// filter the object by relevant keys
				const filteredTranslation = Object.fromEntries(Object.entries(mappedJSON).filter(([key, value]) => relevantKeys.includes(key)))
				return {
					code: 'export default ' + JSON.stringify(filteredTranslation),
					map: { mappings: '' } // provide source map if available
				}
			}
		}
	}
}
