import { paraglideVitePlugin } from '@inlang/paraglide-js';
import devtoolsJson from 'vite-plugin-devtools-json';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';
// loadEnv from 'vite': vitest/config re-exports defineConfig but not loadEnv.
import { loadEnv } from 'vite';
import { playwright } from '@vitest/browser-playwright';
import { sveltekit } from '@sveltejs/kit/vite';

// ORIGIN is the public URL the app is served from (see .env). The dev server
// needs its hostname in allowedHosts, so read it here rather than hardcode it —
// mode '' loads .env regardless of which mode vite is started in.
const ORIGIN = loadEnv('', process.cwd(), '').ORIGIN;

export default defineConfig({
	server: {
		// Vite rejects requests whose Host header it doesn't recognize
		// (DNS-rebinding protection). Nginx forwards the real
		// dev.prospect.medica.im Host through, so that hostname must be
		// allowed or every proxied request comes back "Blocked request".
		allowedHosts: ORIGIN ? [new URL(ORIGIN).hostname] : []
	},
	plugins: [
		tailwindcss(),
		sveltekit(),
		devtoolsJson(),
		paraglideVitePlugin({ project: './project.inlang', outdir: './src/lib/paraglide' })
	],
	test: {
		expect: { requireAssertions: true },
		projects: [
			{
				extends: './vite.config.ts',
				test: {
					name: 'client',
					browser: {
						enabled: true,
						provider: playwright(),
						instances: [{ browser: 'chromium', headless: true }]
					},
					include: ['src/**/*.svelte.{test,spec}.{js,ts}'],
					exclude: ['src/lib/server/**']
				}
			},

			{
				extends: './vite.config.ts',
				test: {
					name: 'server',
					environment: 'node',
					include: ['src/**/*.{test,spec}.{js,ts}'],
					exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
				}
			}
		]
	}
});
