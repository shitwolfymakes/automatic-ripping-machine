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
		setupFiles: ['src/lib/test-setup.ts'],
		// Node 25+ defines a global localStorage that is undefined without
		// --localstorage-file, and it shadows jsdom's; turn Node's off.
		execArgv: ['--no-experimental-webstorage'],
		coverage: {
			provider: 'v8',
			reporter: ['text', 'json', 'lcov'],
			reportsDirectory: 'coverage',
			include: ['src/**/*.{ts,svelte}'],
			exclude: ['src/**/*.test.ts', 'src/**/*.spec.ts', 'src/**/*.d.ts', 'src/lib/types/**', 'src/routes/+layout.ts']
		}
	}
});
