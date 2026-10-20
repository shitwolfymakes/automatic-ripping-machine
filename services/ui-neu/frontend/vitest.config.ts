import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [sveltekit()],
	resolve: {
		conditions: ['browser']
	},
	test: {
		include: ['src/**/*.{test,spec}.{js,ts}'],
		environment: 'jsdom',
		// Node 25+ defines its own global localStorage (undefined without
		// --localstorage-file), which shadows jsdom's. Turn it off so tests use
		// jsdom's. Older Node rejects the flag as a bad option, so gate it.
		execArgv: Number(process.versions.node.split('.')[0]) >= 25 ? ['--no-experimental-webstorage'] : [],
		setupFiles: ['src/lib/test-setup.ts'],
		coverage: {
			provider: 'v8',
			reporter: ['text', 'json', 'lcov'],
			reportsDirectory: 'coverage',
			include: ['src/**/*.{ts,svelte}'],
			exclude: ['src/**/*.test.ts', 'src/**/*.spec.ts', 'src/**/*.d.ts', 'src/lib/types/**', 'src/routes/+layout.ts']
		}
	}
});
