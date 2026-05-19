// SPDX-FileCopyrightText: 2020-present Tobias Kunze
// SPDX-License-Identifier: Apache-2.0

// Single Vite config for both frontend apps bundled with pretalx.
//
// Two same-origin "island" apps — the schedule editor and the public
// schedule — are built into one manifest (`pretalx-manifest.json`) with one
// entry each, and embedded into Django-rendered pages via the
// `{% vite_asset %}` / `{% vite_hmr %}` template tags. One dev server
// (`npm start`) serves both with HMR; one `vite build` produces both.
//
// The public schedule is *also* shipped as a self-contained web component
// for embedding on third-party sites. That is a fundamentally different
// build (UMD, no manifest, custom element, served verbatim by Django), so
// it is a separate `--mode wc` branch here, invoked on its own and never
// part of the dev server or the manifest build.

import path from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import gettext from './schedule-editor/vite-gettext-plugin.js'
import BuntpapierStylus from 'buntpapier/stylus.js'

const EDITOR_SRC = path.resolve(__dirname, 'schedule-editor/src')
const SCHEDULE_SRC = path.resolve(__dirname, 'schedule/src')
const SHARED_STYLES = path.resolve(__dirname, 'shared/styles')

// Both apps reference their own files through the `~` alias. In a single
// shared config one static alias cannot mean two source roots, so resolve
// `~` per importer instead (editor files -> schedule-editor/src, everything
// else -> schedule/src).
function tildeResolver() {
	return {
		name: 'pretalx-tilde-resolver',
		async resolveId(source, importer) {
			if (!importer || !(source === '~' || source.startsWith('~/'))) {
				return null
			}
			const root = importer.includes(`${path.sep}schedule-editor${path.sep}`)
				? EDITOR_SRC
				: SCHEDULE_SRC
			const target = source === '~' ? root : path.join(root, source.slice(2))
			return this.resolve(target, importer, { skipSelf: true })
		},
	}
}

const stylusOptions = {
	paths: [
		SHARED_STYLES,
		path.join(EDITOR_SRC, 'styles'),
		path.join(SCHEDULE_SRC, 'styles'),
		'node_modules',
	],
	use: [BuntpapierStylus({ implicit: false })],
	imports: ['buntpapier/buntpapier/index.styl'],
}

const css = {
	preprocessorOptions: {
		stylus: stylusOptions,
		styl: stylusOptions,
	},
	// buntpapier's stylus plugin is a function and can't be structured-cloned
	// to a worker, so run preprocessors on the main thread.
	preprocessorMaxWorkers: 0,
}

const resolve = {
	mainFields: ['browser', 'module', 'jsnext:main', 'jsnext'],
	extensions: ['.js', '.json', '.vue'],
	alias: [
		{ find: /^buntpapier$/, replacement: 'buntpapier/src/index.js' },
		{
			find: 'moment-timezone',
			replacement:
				'moment-timezone/builds/moment-timezone-with-data-10-year-range.js',
		},
	],
}

export default defineConfig(({ mode }) => {
	if (mode === 'wc') {
		// Embeddable web component for third-party sites: one self-contained
		// UMD file that Django serves verbatim under a stable per-event URL.
		return {
			define: {
				'process.env.NODE_ENV': JSON.stringify(
					process.env.NODE_ENV || 'production'
				),
				// The app uses the Options API; keep that flag on, strip the
				// rest of Vue's dev-only code paths from the embedded bundle.
				__VUE_OPTIONS_API__: 'true',
				__VUE_PROD_DEVTOOLS__: 'false',
				__VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false',
			},
			plugins: [
				tildeResolver(),
				vue({
					template: {
						compilerOptions: {
							isCustomElement: (tag) => tag === 'pretalx-schedule',
						},
					},
					features: {
						customElement: true,
					},
				}),
			],
			css,
			resolve,
			build: {
				// Built into the agenda static source dir so the widget view
				// (pretalx.agenda.views.widget) finds it via staticfiles in
				// dev and after collectstatic in production.
				outDir: path.resolve(__dirname, '../static/agenda/js'),
				emptyOutDir: false,
				assetsDir: '',
				lib: {
					entry: path.resolve(SCHEDULE_SRC, 'main-wc.js'),
					name: 'PretalxSchedule',
					formats: ['umd'],
					fileName: () => 'pretalx-schedule.min.js',
				},
				target: 'es2022',
			},
		}
	}

	// Dev server + manifest build for the same-origin apps.
	return {
		base: process.env.BASE_URL || '/',
		plugins: [tildeResolver(), gettext(), vue()],
		css,
		resolve,
		build: {
			// OUT_DIR is injected by `rebuild`/the wheel build; the fallback
			// keeps a bare `vite build` (or `just npm build`) working.
			outDir:
				process.env.OUT_DIR ||
				path.resolve(__dirname, 'schedule-editor/dist'),
			emptyOutDir: false,
			manifest: 'pretalx-manifest.json',
			assetsDir: '',
			rollupOptions: {
				input: {
					'schedule-editor': path.resolve(EDITOR_SRC, 'main.js'),
					schedule: path.resolve(SCHEDULE_SRC, 'main.js'),
				},
				output: {
					// Vite 8 (rolldown) only accepts `manualChunks` as a
					// function; the old object form is no longer supported.
					manualChunks(id) {
						if (id.includes('moment')) return 'moment'
					},
				},
			},
			target: 'es2022',
		},
		optimizeDeps: {
			exclude: ['moment', 'buntpapier'],
			include: ['buntpapier > fuzzysearch'],
		},
		server: {
			port: 8080,
		},
	}
})
